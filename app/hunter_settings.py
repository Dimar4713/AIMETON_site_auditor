from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Literal

from pydantic import BaseModel, Field

from app.models import HuntRequest


SETTINGS_KEY = "hunter.settings.v1"


class HunterSettings(BaseModel):
    max_queries: int = Field(default=20, ge=1, le=100)
    results_per_query: int = Field(default=10, ge=1, le=30)
    max_candidates: int = Field(default=100, ge=1, le=500)
    minimum_pre_score: int = Field(default=35, ge=0, le=100)
    deep_audit_score: int = Field(default=60, ge=0, le=100)
    output_limit: int = Field(default=25, ge=1, le=100)
    concurrency: int = Field(default=4, ge=1, le=12)
    provider_strategy: Literal["fallback_first_nonempty"] = "fallback_first_nonempty"

    def validate_relationships(self) -> None:
        if self.deep_audit_score < self.minimum_pre_score:
            raise ValueError("deep_audit_score must be >= minimum_pre_score")
        if self.output_limit > self.max_candidates:
            raise ValueError("output_limit must be <= max_candidates")


class HunterSettingsRecord(BaseModel):
    settings: HunterSettings = Field(default_factory=HunterSettings)
    updated_at: str | None = None
    updated_by: int | None = None
    reason: str | None = None


class HunterSettingsRepository:
    """Legacy compatibility facade.

    Persistent v1 storage remains readable for rollback, but new Hunter runtime
    limits are sourced from the active Search Strategy tariff profile so there is
    only one effective configuration path.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        configured = path or os.getenv("AIMETON_RUNTIME_DB", "data/runtime-core.sqlite3")
        self.path = Path(configured)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _ensure_schema(self) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )

    def get(self) -> HunterSettingsRecord:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT value FROM runtime_meta WHERE key = ?", (SETTINGS_KEY,)).fetchone()
        if row is None:
            return HunterSettingsRecord()
        try:
            return HunterSettingsRecord.model_validate_json(row["value"])
        except Exception:
            return HunterSettingsRecord()

    def save(self, settings: HunterSettings, *, actor_id: int, reason: str) -> HunterSettingsRecord:
        settings.validate_relationships()
        normalized_reason = " ".join(reason.split())
        if not normalized_reason:
            raise ValueError("reason_required")
        record = HunterSettingsRecord(
            settings=settings,
            updated_at=datetime.now(UTC).isoformat(),
            updated_by=actor_id,
            reason=normalized_reason[:500],
        )
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO runtime_meta(key, value) VALUES(?, ?)",
                (SETTINGS_KEY, record.model_dump_json()),
            )
        return record

    def apply(self, request: HuntRequest) -> HuntRequest:
        from app.search_strategy_settings import get_search_strategy_settings_repository

        strategy_record = get_search_strategy_settings_repository().get()
        strategy_record.settings.validate_relationships()
        return strategy_record.settings.apply_hunt_request(request)


def get_hunter_settings_repository() -> HunterSettingsRepository:
    return HunterSettingsRepository()
