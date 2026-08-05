from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping

from app.retention_audit import SQLiteRetentionAuditLedger
from app.retention_runner import RetentionPeriodicRunner, RetentionRunnerConfig
from app.retention_service import RetentionLifecycleOwner
from app.retention_worker import RetentionCleanupWorker
from app.trace_ledger import SQLiteTraceLedger


_TRUE_VALUES = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class RetentionRuntimeConfig:
    enabled: bool = False
    interval_seconds: float = 3600.0
    batch_size: int = 1000
    max_batches: int = 10
    max_runtime_seconds: float = 2.0


def _parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in _TRUE_VALUES


def retention_runtime_config_from_env(
    env: Mapping[str, str] | None = None,
) -> RetentionRuntimeConfig:
    values = env or os.environ
    return RetentionRuntimeConfig(
        enabled=_parse_bool(values.get("AIMETON_RETENTION_ENABLED"), default=False),
        interval_seconds=float(values.get("AIMETON_RETENTION_INTERVAL_SECONDS", "3600")),
        batch_size=int(values.get("AIMETON_RETENTION_BATCH_SIZE", "1000")),
        max_batches=int(values.get("AIMETON_RETENTION_MAX_BATCHES", "10")),
        max_runtime_seconds=float(values.get("AIMETON_RETENTION_MAX_RUNTIME_SECONDS", "2")),
    )


def build_retention_runner(
    runtime_db_path: str | Path,
    *,
    config: RetentionRuntimeConfig | None = None,
) -> RetentionPeriodicRunner:
    """Build the one retention runner used by the application lifecycle.

    The returned runner remains disabled unless explicitly enabled in config.
    SQLite trace and audit ledgers intentionally share the durable runtime DB.
    """
    resolved = config or retention_runtime_config_from_env()
    path = Path(runtime_db_path)
    worker = RetentionCleanupWorker(
        SQLiteTraceLedger(path),
        batch_size=resolved.batch_size,
        max_batches=resolved.max_batches,
        max_runtime_seconds=resolved.max_runtime_seconds,
    )
    owner = RetentionLifecycleOwner(worker, SQLiteRetentionAuditLedger(path))
    return RetentionPeriodicRunner(
        owner,
        config=RetentionRunnerConfig(
            enabled=resolved.enabled,
            interval_seconds=resolved.interval_seconds,
        ),
    )
