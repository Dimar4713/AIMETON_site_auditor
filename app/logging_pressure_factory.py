from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping

from app.linux_resource_snapshot import LinuxResourceSnapshotProvider
from app.logging_pressure import LoggingPressureController, PressurePolicy
from app.logging_pressure_audit import SQLiteLoggingPressureAudit
from app.logging_pressure_runtime import LoggingPressureRuntimeOwner
from app.logging_pressure_sampler import (
    LoggingPressureSampler,
    LoggingPressureSamplerConfig,
)
from app.trace_write_metrics import trace_pressure_callbacks


_TRUE_VALUES = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class LoggingPressureRuntimeConfig:
    enabled: bool = False
    interval_seconds: float = 60.0
    disk_path: str = "/app/data"
    recovery_samples: int = 3


@dataclass(frozen=True)
class LoggingPressureRuntime:
    owner: LoggingPressureRuntimeOwner
    sampler: LoggingPressureSampler


def _parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in _TRUE_VALUES


def logging_pressure_config_from_env(
    env: Mapping[str, str] | None = None,
) -> LoggingPressureRuntimeConfig:
    values = env or os.environ
    return LoggingPressureRuntimeConfig(
        enabled=_parse_bool(values.get("AIMETON_LOGGING_PRESSURE_ENABLED"), default=False),
        interval_seconds=float(
            values.get("AIMETON_LOGGING_PRESSURE_INTERVAL_SECONDS", "60")
        ),
        disk_path=values.get("AIMETON_LOGGING_PRESSURE_DISK_PATH", "/app/data"),
        recovery_samples=int(
            values.get("AIMETON_LOGGING_PRESSURE_RECOVERY_SAMPLES", "3")
        ),
    )


def build_logging_pressure_runtime(
    runtime_db_path: str | Path,
    *,
    config: LoggingPressureRuntimeConfig | None = None,
) -> LoggingPressureRuntime:
    resolved = config or logging_pressure_config_from_env()
    owner = LoggingPressureRuntimeOwner(
        LoggingPressureController(
            policy=PressurePolicy(recovery_samples=resolved.recovery_samples)
        ),
        SQLiteLoggingPressureAudit(runtime_db_path),
    )
    queue_depth, write_p95_ms = trace_pressure_callbacks(runtime_db_path)
    sampler = LoggingPressureSampler(
        owner,
        LinuxResourceSnapshotProvider(
            disk_path=resolved.disk_path,
            queue_depth=queue_depth,
            write_p95_ms=write_p95_ms,
        ),
        config=LoggingPressureSamplerConfig(
            enabled=resolved.enabled,
            interval_seconds=resolved.interval_seconds,
        ),
    )
    return LoggingPressureRuntime(owner=owner, sampler=sampler)
