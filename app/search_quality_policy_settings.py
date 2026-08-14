from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
import sqlite3
from threading import RLock

from pydantic import BaseModel, Field

from app.search_observer_quality_policy import QualityFirstPromotionPolicy


SETTINGS_KEY = "search.quality.policy.v1"


class SearchQualityPolicyRecord(BaseModel):
    policy: QualityFirstPromotionPolicy = Field(default_factory=QualityFirstPromotionPolicy)
    updated_at: str | None = None
    updated_by: int | None = None
    reason: str | None = None


class SearchQualityPolicyRepository:
    """Persistent owner/admin policy for search quality promotion guards.

    The values belong to the administrative control plane. They are never
    exposed as user search-regime parameters and do not change routing by
    themselves.
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
            db.execute("CREATE TABLE IF NOT EXISTS runtime_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    def get(self) -> SearchQualityPolicyRecord:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT value FROM runtime_meta WHERE key = ?", (SETTINGS_KEY,)).fetchone()
        if row is None:
            return SearchQualityPolicyRecord()
        try:
            return SearchQualityPolicyRecord.model_validate_json(row["value"])
        except Exception:
            return SearchQualityPolicyRecord()

    def save(
        self,
        policy: QualityFirstPromotionPolicy,
        *,
        actor_id: int,
        reason: str,
    ) -> SearchQualityPolicyRecord:
        normalized_reason = " ".join(reason.split())
        if not normalized_reason:
            raise ValueError("reason_required")
        record = SearchQualityPolicyRecord(
            policy=policy,
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


def get_search_quality_policy_repository() -> SearchQualityPolicyRepository:
    return SearchQualityPolicyRepository()
