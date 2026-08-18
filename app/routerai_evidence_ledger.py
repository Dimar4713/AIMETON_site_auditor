from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

from app.mission_sqlite import SQLiteMissionRepository
from app.trace_context import current_trace_identity

if TYPE_CHECKING:
    from app.routerai_profile_extraction import MergedProfileExtraction


EVIDENCE_LEDGER_SCHEMA_VERSION = 1


class EvidenceLedgerPersistenceError(RuntimeError):
    """Canonical mission exists but the structured evidence ledger was not durable."""


def evidence_ledger_payload(merged: "MergedProfileExtraction") -> dict[str, Any]:
    """Build a recoverable structured ledger without raw prompts/provider payloads."""
    return {
        "schema_version": EVIDENCE_LEDGER_SCHEMA_VERSION,
        "company_name": merged.company_name,
        "business_summary": merged.business_summary,
        "evidence": list(merged.evidence),
        "company_facts": [item.model_dump(mode="json") for item in merged.company_facts],
        "economic_signals": [item.model_dump(mode="json") for item in merged.economic_signals],
        "risks_and_assumptions": list(merged.risks_and_assumptions),
        "coverage": merged.coverage.safe_dict(),
    }


def evidence_ledger_digest(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def persist_merged_evidence_ledger(
    merged: "MergedProfileExtraction",
    *,
    repository: SQLiteMissionRepository | None = None,
) -> str | None:
    """Persist one idempotent evidence-ledger record for the current mission attempt.

    Direct/non-mission calls intentionally skip persistence. Once a canonical mission is
    bound, a storage failure is fail-closed: reasoning must not claim a complete result
    whose full extracted ledger cannot be recovered.
    """
    identity = current_trace_identity()
    if identity is None:
        return None

    repo = repository or SQLiteMissionRepository()
    mission = repo.get_for_admin(identity.mission_id)
    if mission is None:
        return None

    record_id = f"evidence_ledger_{identity.attempt_id}"
    existing = repo.records_for_owner(mission.owner_id, mission.id) or []
    for record in existing:
        if record.get("id") == record_id:
            if record.get("kind") != "evidence_ledger":
                raise EvidenceLedgerPersistenceError("evidence_ledger_record_id_collision")
            return record_id

    payload = evidence_ledger_payload(merged)
    digest = evidence_ledger_digest(payload)
    try:
        return repo.append_record(
            mission.id,
            "evidence_ledger",
            payload,
            digest=digest,
            record_id=record_id,
        )
    except Exception as exc:
        raise EvidenceLedgerPersistenceError("evidence_ledger_persist_failed") from exc
