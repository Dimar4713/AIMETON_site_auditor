from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.trace_ledger import RetentionClass, TraceEventCreate, TraceState
from app.trace_write_metrics import InstrumentedSQLiteTraceLedger


def persist_hunter_professional_provenance(
    *,
    mission_id: str,
    attempt_id: str,
    brief_revision: str,
    brief_snapshot: dict[str, Any],
    actual_gateway_policy: dict[str, Any],
    configured_admin_policy_fingerprint: str | None,
    projected_admin_gateway_policy: dict[str, Any] | None,
    quality_policy_fingerprint: str | None,
    trace_db_path: str | Path | None = None,
) -> bool:
    """Persist an observability-only bridge from legacy Hunter to Professional Core.

    The event is intentionally non-authoritative and fail-open. It records what
    scope and gateway policy were actually used, plus whether the configured
    admin strategy would resolve to the same gateway policy. No policy is applied
    or changed here.
    """
    configured = trace_db_path or os.getenv(
        "AIMETON_TRACE_DB",
        os.getenv("AIMETON_RUNTIME_DB", "data/runtime-core.sqlite3"),
    )
    try:
        ledger = InstrumentedSQLiteTraceLedger(configured)
        projected_fingerprint = (
            str(projected_admin_gateway_policy.get("fingerprint"))
            if projected_admin_gateway_policy
            else None
        )
        actual_fingerprint = str(actual_gateway_policy.get("fingerprint") or "")
        ledger.append(
            TraceEventCreate(
                mission_id=mission_id,
                attempt_id=attempt_id,
                component="professional_configuration_bridge",
                operation="legacy_hunter_scope_and_policy_resolved",
                state=TraceState.SUCCEEDED,
                reason_code="legacy_hunter_professional_provenance_observed",
                summary="Legacy Hunter effective scope and applied/configured policy fingerprints retained without routing change",
                counters={"brief_schema_version": 1},
                metadata={
                    "brief_revision": brief_revision,
                    "brief_schema": brief_snapshot.get("schema"),
                    "brief_geographies": brief_snapshot.get("geographies", []),
                    "brief_industries": brief_snapshot.get("industries", []),
                    "brief_focus": brief_snapshot.get("focus", []),
                    "actual_gateway_policy_fingerprint": actual_fingerprint,
                    "actual_provider_order": actual_gateway_policy.get("provider_order", []),
                    "actual_strategy": actual_gateway_policy.get("strategy"),
                    "actual_allow_paid_fallback": actual_gateway_policy.get("allow_paid_fallback"),
                    "actual_allow_paid_fanout": actual_gateway_policy.get("allow_paid_fanout"),
                    "configured_admin_policy_fingerprint": configured_admin_policy_fingerprint,
                    "projected_admin_gateway_policy_fingerprint": projected_fingerprint,
                    "configured_admin_policy_applied_to_gateway": bool(
                        projected_fingerprint and projected_fingerprint == actual_fingerprint
                    ),
                    "quality_policy_fingerprint": quality_policy_fingerprint,
                    "quality_policy_applied_to_routing": False,
                    "routing_changed": False,
                    "steering_enabled": False,
                },
                event_key=(
                    f"{mission_id}:{attempt_id}:professional-configuration-bridge:scope-policy"
                )[:256],
                retention_class=RetentionClass.TRACE,
            )
        )
        return True
    except Exception:
        return False
