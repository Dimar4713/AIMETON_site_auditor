from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


TimeQuality = Literal["trusted", "degraded", "fallback"]
TimeHealthStatus = Literal["ok", "degraded", "failed"]


class RuntimeTimeSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    utc: str
    unix_ms: int = Field(ge=0)
    source: str = Field(min_length=1, max_length=32)
    synced: bool
    offset_ms: float | None = None
    stratum: int | None = Field(default=None, ge=0, le=16)
    quality: TimeQuality
    reason_code: str | None = Field(default=None, max_length=64)


class RuntimeTimeHealth(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: TimeHealthStatus
    synced: bool
    quality: TimeQuality
    offset_ms: float | None = None
    stratum: int | None = None
    max_offset_ms: float = Field(ge=0)
    max_stratum: int = Field(ge=1, le=16)
    reason_code: str | None = None


def _utc_now() -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    return now.isoformat(timespec="milliseconds").replace("+00:00", "Z"), time.time_ns() // 1_000_000


def _safe_status_path() -> Path | None:
    value = os.getenv("AIMETON_TIME_STATUS_FILE", "").strip()
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        return None
    return path


def _fallback(utc: str, unix_ms: int, reason_code: str) -> RuntimeTimeSnapshot:
    return RuntimeTimeSnapshot(
        utc=utc,
        unix_ms=unix_ms,
        source="system_clock",
        synced=False,
        quality="fallback",
        reason_code=reason_code,
    )


def runtime_time_snapshot() -> RuntimeTimeSnapshot:
    utc, unix_ms = _utc_now()
    path = _safe_status_path()
    if path is None or not path.is_file():
        return _fallback(utc, unix_ms, "canonical_status_unavailable")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _fallback(utc, unix_ms, "canonical_status_invalid")
    if not isinstance(payload, dict):
        return _fallback(utc, unix_ms, "canonical_status_invalid")

    try:
        synced = bool(payload["synced"])
        offset_ms = float(payload["offset_ms"])
        stratum = int(payload["stratum"])
        source = str(payload.get("source", "chrony"))
    except (KeyError, TypeError, ValueError):
        return _fallback(utc, unix_ms, "canonical_status_invalid")

    max_offset = float(os.getenv("AIMETON_TIME_MAX_OFFSET_MS", "50"))
    max_stratum = int(os.getenv("AIMETON_TIME_MAX_STRATUM", "4"))
    within_policy = synced and abs(offset_ms) <= max_offset and stratum <= max_stratum
    return RuntimeTimeSnapshot(
        utc=utc,
        unix_ms=unix_ms,
        source=source[:32] or "chrony",
        synced=synced,
        offset_ms=offset_ms,
        stratum=stratum,
        quality="trusted" if within_policy else "degraded",
        reason_code=None if within_policy else "time_policy_not_satisfied",
    )


def runtime_time_health() -> RuntimeTimeHealth:
    snapshot = runtime_time_snapshot()
    max_offset = float(os.getenv("AIMETON_TIME_MAX_OFFSET_MS", "50"))
    max_stratum = int(os.getenv("AIMETON_TIME_MAX_STRATUM", "4"))
    require_sync = os.getenv("AIMETON_TIME_REQUIRE_SYNC", "true").strip().lower() not in {
        "0",
        "false",
        "no",
    }
    if snapshot.quality == "trusted":
        status: TimeHealthStatus = "ok"
    elif require_sync:
        status = "failed"
    else:
        status = "degraded"
    return RuntimeTimeHealth(
        status=status,
        synced=snapshot.synced,
        quality=snapshot.quality,
        offset_ms=snapshot.offset_ms,
        stratum=snapshot.stratum,
        max_offset_ms=max_offset,
        max_stratum=max_stratum,
        reason_code=snapshot.reason_code,
    )
