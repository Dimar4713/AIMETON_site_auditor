from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import User
from app.auth_api import require_admin


router = APIRouter(prefix="/api/admin/missions", tags=["admin-trace"])

_STAGE_OPERATIONS = {
    "selected": {"provider_selected", "selected"},
    "called": {"request_started", "provider_called", "request_sent"},
    "returned": {"response_received", "provider_returned", "results_received"},
    "accepted": {"evidence_accepted", "results_accepted", "accepted"},
    "used_in_report": {"used_in_report", "report_evidence_used", "report_used"},
}


class ProviderStageProjection(BaseModel):
    reached: bool
    sequence: int | None = Field(default=None, ge=1)
    state: str | None = None
    reason_code: str | None = None
    counters: dict[str, int] = Field(default_factory=dict)


class ProviderWaterfallProjection(BaseModel):
    provider: str
    selected: ProviderStageProjection
    called: ProviderStageProjection
    returned: ProviderStageProjection
    accepted: ProviderStageProjection
    used_in_report: ProviderStageProjection
    first_sequence: int = Field(ge=1)
    last_sequence: int = Field(ge=1)
    terminal_reason: str | None = None


def _connect() -> sqlite3.Connection:
    path = Path(os.getenv("AIMETON_RUNTIME_DB", "data/runtime-core.sqlite3"))
    if not path.exists():
        raise HTTPException(status_code=503, detail={"reason": "trace_ledger_unavailable"})
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    return db


def _empty_stage() -> ProviderStageProjection:
    return ProviderStageProjection(reached=False)


@router.get(
    "/{mission_id}/trace/attempts/{attempt_id}/provider-waterfall",
    response_model=list[ProviderWaterfallProjection],
)
def provider_waterfall(
    mission_id: str,
    attempt_id: str,
    _admin: User = Depends(require_admin),
) -> list[ProviderWaterfallProjection]:
    with _connect() as db:
        rows = db.execute(
            """
            SELECT sequence, provider, operation, state, reason_code, counters_json
            FROM mission_trace_events
            WHERE mission_id = ? AND attempt_id = ? AND provider IS NOT NULL
            ORDER BY sequence
            LIMIT 2000
            """,
            (mission_id, attempt_id),
        ).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail={"reason": "provider_trace_not_found"})

    providers: dict[str, dict[str, object]] = {}
    for row in rows:
        provider = row["provider"]
        entry = providers.setdefault(
            provider,
            {
                "first_sequence": row["sequence"],
                "last_sequence": row["sequence"],
                "terminal_reason": None,
                **{stage: _empty_stage() for stage in _STAGE_OPERATIONS},
            },
        )
        entry["last_sequence"] = row["sequence"]
        if row["state"] in {"failed", "blocked", "degraded", "cancelled"}:
            entry["terminal_reason"] = row["reason_code"]
        for stage, operations in _STAGE_OPERATIONS.items():
            if row["operation"] in operations and not entry[stage].reached:
                entry[stage] = ProviderStageProjection(
                    reached=True,
                    sequence=row["sequence"],
                    state=row["state"],
                    reason_code=row["reason_code"],
                    counters=json.loads(row["counters_json"]),
                )

    return [
        ProviderWaterfallProjection(provider=provider, **entry)
        for provider, entry in sorted(
            providers.items(), key=lambda item: int(item[1]["first_sequence"])
        )
    ]
