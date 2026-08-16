from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from app.hunter_professional_provenance import (
    build_legacy_hunter_brief_snapshot_from_scope,
    legacy_hunter_brief_revision_from_snapshot,
)
from app.trace_ledger import RetentionClass, TraceEventCreate, TraceState
from app.trace_write_metrics import InstrumentedSQLiteTraceLedger


_URL_LIMIT = 1500
_TITLE_LIMIT = 500


def diagnostic_url(value: str) -> str:
    """Keep only the public URL identity; drop query/fragment tracking material."""
    try:
        parts = urlsplit(value)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))[:_URL_LIMIT]
    except Exception:
        return value[:_URL_LIMIT]


def _compact_recommendation_controls_json(evidence: dict[str, object]) -> str:
    raw = evidence.get("recommendations")
    if not isinstance(raw, list):
        return "[]"
    controls: list[dict[str, object]] = []
    for item in raw[:40]:
        if not isinstance(item, dict):
            continue
        try:
            controls.append(
                {
                    "direction_index": int(item["direction_index"]),
                    "action": str(item["action"]),
                    "confidence": float(item["confidence"]),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return json.dumps(controls, ensure_ascii=False, separators=(",", ":"))


class HunterForensicTrace:
    """Fail-open 24h Hunter candidate funnel diagnostics.

    This is diagnostic only. It must never become authoritative state and must
    never make a successful hunt fail because observability is unavailable.
    """

    def __init__(
        self,
        mission_id: str,
        attempt_id: str,
        *,
        trace_db_path: str | Path | None = None,
    ) -> None:
        configured = trace_db_path or os.getenv(
            "AIMETON_TRACE_DB",
            os.getenv("AIMETON_RUNTIME_DB", "data/runtime-core.sqlite3"),
        )
        self.mission_id = mission_id
        self.attempt_id = attempt_id
        self.runtime_version = os.getenv("AIMETON_RUNTIME_VERSION") or None
        self.ledger = InstrumentedSQLiteTraceLedger(configured)
        self._counter = 0

    def _retain_effective_brief(self, metadata: dict[str, object]) -> None:
        """Retain the effective legacy Hunter brief as a longer-lived bridge event."""
        try:
            snapshot = build_legacy_hunter_brief_snapshot_from_scope(
                region=str(metadata.get("effective_region") or ""),
                search_zone=(
                    str(metadata["search_zone"])
                    if metadata.get("search_zone")
                    else None
                ),
                industries=(
                    metadata.get("effective_industries")
                    if isinstance(metadata.get("effective_industries"), list)
                    else []
                ),
                focus=(
                    metadata.get("effective_focus")
                    if isinstance(metadata.get("effective_focus"), list)
                    else []
                ),
            )
            revision = legacy_hunter_brief_revision_from_snapshot(snapshot)
            self.ledger.append(
                TraceEventCreate(
                    mission_id=self.mission_id,
                    attempt_id=self.attempt_id,
                    component="professional_configuration_bridge",
                    operation="legacy_hunter_brief_resolved",
                    state=TraceState.SUCCEEDED,
                    reason_code="legacy_hunter_effective_brief_retained",
                    summary="Effective legacy Hunter business scope retained as content-addressed Mission Brief bridge",
                    counters={"brief_schema_version": 1},
                    metadata={
                        "brief_revision": revision,
                        "brief_schema": snapshot["schema"],
                        "geographies": snapshot["geographies"],
                        "industries": snapshot["industries"],
                        "focus": snapshot["focus"],
                        "entity_types": snapshot["entity_types"],
                        "authoritative_product_state": False,
                        "routing_changed": False,
                        "steering_enabled": False,
                    },
                    event_key=(
                        f"{self.mission_id}:{self.attempt_id}:professional-configuration-bridge:brief"
                    )[:256],
                    runtime_version=self.runtime_version,
                    retention_class=RetentionClass.TRACE,
                )
            )
        except Exception:
            pass

    def append(
        self,
        operation: str,
        *,
        state: TraceState,
        reason_code: str,
        summary: str,
        identity: str = "global",
        url: str | None = None,
        title: str | None = None,
        counters: dict[str, int] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self._counter += 1
        safe_metadata = dict(metadata or {})
        if operation == "hunt_plan":
            self._retain_effective_brief(safe_metadata)
        if operation == "hunt_search_wave_shadow_observer":
            try:
                from app.search_observer_llm import get_last_shadow_observer_evidence

                observer_evidence = get_last_shadow_observer_evidence()
                safe_metadata.update(observer_evidence)
                safe_metadata["recommendation_controls_json"] = _compact_recommendation_controls_json(observer_evidence)
            except Exception:
                pass
        if url:
            safe_metadata["candidate_url"] = diagnostic_url(url)
        if title:
            safe_metadata["candidate_title"] = title[:_TITLE_LIMIT]
        try:
            self.ledger.append(
                TraceEventCreate(
                    mission_id=self.mission_id,
                    attempt_id=self.attempt_id,
                    component="hunter",
                    operation=operation,
                    state=state,
                    reason_code=reason_code,
                    summary=summary,
                    counters=counters or {},
                    metadata=safe_metadata,
                    event_key=(
                        f"{self.mission_id}:{self.attempt_id}:hunter:"
                        f"{self._counter}:{identity}:{operation}"
                    )[:256],
                    runtime_version=self.runtime_version,
                    retention_class=RetentionClass.FORENSIC,
                )
            )
        except Exception:
            pass
