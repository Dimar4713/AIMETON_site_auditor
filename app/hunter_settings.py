from __future__ import annotations

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
    """Compatibility facade over the active tariff Search Strategy profile."""

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
            db.execute("CREATE TABLE IF NOT EXISTS runtime_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    def _strategy_repository(self):
        from app.search_strategy_settings import SearchStrategySettingsRepository

        return SearchStrategySettingsRepository(self.path)

    @staticmethod
    def _project(record) -> HunterSettingsRecord:
        profile = record.settings.active_profile()
        return HunterSettingsRecord(
            settings=HunterSettings(
                max_queries=profile.max_queries,
                results_per_query=profile.results_per_query,
                max_candidates=profile.max_candidates,
                minimum_pre_score=profile.minimum_pre_score,
                deep_audit_score=profile.deep_audit_score,
                output_limit=profile.output_limit,
                concurrency=profile.concurrency,
                provider_strategy="fallback_first_nonempty",
            ),
            updated_at=record.updated_at,
            updated_by=record.updated_by,
            reason=record.reason,
        )

    def get(self) -> HunterSettingsRecord:
        return self._project(self._strategy_repository().get())

    def save(self, settings: HunterSettings, *, actor_id: int, reason: str) -> HunterSettingsRecord:
        settings.validate_relationships()
        repository = self._strategy_repository()
        record = repository.get()
        strategy_settings = record.settings.model_copy(deep=True)
        profile_id = strategy_settings.global_settings.active_tariff
        strategy_settings.tariffs[profile_id] = strategy_settings.tariffs[profile_id].model_copy(
            update={
                "max_queries": settings.max_queries,
                "results_per_query": settings.results_per_query,
                "max_candidates": settings.max_candidates,
                "minimum_pre_score": settings.minimum_pre_score,
                "deep_audit_score": settings.deep_audit_score,
                "output_limit": settings.output_limit,
                "concurrency": settings.concurrency,
            }
        )
        saved = repository.save(strategy_settings, actor_id=actor_id, reason=reason)
        return self._project(saved)

    def apply(self, request: HuntRequest) -> HuntRequest:
        record = self._strategy_repository().get()
        record.settings.validate_relationships()
        return record.settings.apply_hunt_request(request)


def get_hunter_settings_repository() -> HunterSettingsRepository:
    return HunterSettingsRepository()
