from pathlib import Path

import pytest

from app.trace_ledger import SQLiteTraceLedger, TraceEventCreate, TraceState
from scripts.search_gap_trace_replay_report import build_trace_replay_report


def _append(
    ledger: SQLiteTraceLedger,
    key: str,
    *,
    component: str,
    operation: str,
    metadata: dict,
) -> None:
    ledger.append(
        TraceEventCreate(
            mission_id="hunt-cli-replay",
            attempt_id="corr-cli-replay",
            component=component,
            operation=operation,
            state=TraceState.SUCCEEDED,
            reason_code="test",
            metadata=metadata,
            event_key=key,
        )
    )


def test_trace_replay_report_reads_retained_attempt_and_scores_quality(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    db = tmp_path / "runtime.sqlite3"
    ledger = SQLiteTraceLedger(db)
    _append(
        ledger,
        "planned",
        component="search_gateway",
        operation="query_planned",
        metadata={"query_index": 11, "query_text": "стоматология Красноярск"},
    )
    _append(
        ledger,
        "result",
        component="search_gateway",
        operation="result_item",
        metadata={"query_index": 11, "result_url": "https://clinic.ru/"},
    )
    _append(
        ledger,
        "candidate",
        component="hunter",
        operation="candidate_returned",
        metadata={
            "candidate_url": "https://clinic.ru/",
            "source_role": "direct_candidate",
            "region_confirmed": True,
            "industry_match": 25,
        },
    )

    def mutable_init_must_not_run(*_args, **_kwargs):
        raise AssertionError("mutable SQLiteTraceLedger initialization is forbidden during replay")

    monkeypatch.setattr(SQLiteTraceLedger, "__init__", mutable_init_must_not_run)
    report = build_trace_replay_report(
        db,
        mission_id="hunt-cli-replay",
        attempt_id="corr-cli-replay",
        gap_code="region_confirmation_missing",
        effective_regime="balanced",
        suggested_follow_up_query="стоматология Красноярск",
    )

    assert report["case_found"] is True
    assert report["record_count"] == 1
    assert report["assessments"][0]["verdict"] == "supported"
    assert report["routing_changed"] is False
    assert report["steering_enabled"] is False
    assert report["promotion_activated"] is False


def test_trace_replay_report_is_fail_closed_when_query_is_not_retained(tmp_path: Path):
    db = tmp_path / "runtime.sqlite3"
    SQLiteTraceLedger(db)

    report = build_trace_replay_report(
        db,
        mission_id="hunt-cli-replay",
        attempt_id="corr-cli-replay",
        gap_code="sparse_yield",
        effective_regime="discovery",
        suggested_follow_up_query="missing query",
    )

    assert report == {
        "evidence_kind": "search_gap_trace_replay",
        "mission_id": "hunt-cli-replay",
        "attempt_id": "corr-cli-replay",
        "case_found": False,
        "record_count": 0,
        "routing_changed": False,
        "steering_enabled": False,
        "promotion_activated": False,
    }
