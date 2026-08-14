from datetime import UTC, datetime

from app.search_gap_hindsight import GapHindsightVerdict
from app.search_gap_trace_replay import replay_case_from_trace
from app.trace_ledger import TraceEvent, TraceState


def _event(seq: int, component: str, operation: str, metadata: dict) -> TraceEvent:
    return TraceEvent(
        event_id=f"event-{seq}",
        event_key=f"event-key-{seq}",
        mission_id="hunt-trace-replay",
        attempt_id="corr-trace-replay",
        sequence=seq,
        component=component,
        operation=operation,
        state=TraceState.SUCCEEDED,
        reason_code="test",
        metadata=metadata,
        metadata_digest=f"digest-{seq}",
        created_at=datetime.now(UTC),
    )


def _planned(seq: int, index: int, query: str) -> TraceEvent:
    return _event(seq, "search_gateway", "query_planned", {"query_index": index, "query_text": query})


def _result(seq: int, index: int, url: str) -> TraceEvent:
    return _event(seq, "search_gateway", "result_item", {"query_index": index, "result_url": url})


def _candidate(seq: int, url: str, *, region: bool | None = None, industry: int | None = None) -> TraceEvent:
    return _event(
        seq,
        "hunter",
        "candidate_returned",
        {
            "candidate_url": url,
            "source_role": "direct_candidate",
            "region_confirmed": region,
            "industry_match": industry,
        },
    )


def test_sparse_replay_uses_exact_retained_query_and_new_domain_yield():
    events = [
        _planned(1, 7, "стоматология Красноярск официальный сайт"),
        _result(2, 7, "https://new-dent.ru/services"),
    ]
    case = replay_case_from_trace(
        events,
        gap_code="sparse_yield",
        effective_regime="discovery",
        suggested_follow_up_query="  СТОМАТОЛОГИЯ   Красноярск официальный сайт ",
        baseline_domains=["known-dent.ru"],
    )
    assert case is not None
    outcome = case.to_retained_outcome()
    assessment = outcome.assess()
    assert outcome.evidence.added_unique_domains == 1
    assert assessment.verdict == GapHindsightVerdict.SUPPORTED


def test_region_and_industry_replay_use_final_candidate_quality_evidence():
    events = [
        _planned(1, 4, "стоматология Красноярск"),
        _result(2, 4, "https://clinic.ru/"),
        _candidate(3, "https://clinic.ru/", region=True, industry=25),
    ]
    region_case = replay_case_from_trace(
        events,
        gap_code="region_confirmation_missing",
        effective_regime="balanced",
        suggested_follow_up_query="стоматология Красноярск",
    )
    industry_case = replay_case_from_trace(
        events,
        gap_code="industry_confirmation_missing",
        effective_regime="balanced",
        suggested_follow_up_query="стоматология Красноярск",
    )
    assert region_case is not None and industry_case is not None
    assert region_case.to_retained_outcome().assess().verdict == GapHindsightVerdict.SUPPORTED
    assert industry_case.to_retained_outcome().assess().verdict == GapHindsightVerdict.SUPPORTED


def test_quality_replay_fails_closed_when_candidate_domain_has_multi_query_lineage():
    events = [
        _planned(1, 1, "first query"),
        _planned(2, 2, "second query"),
        _result(3, 1, "https://shared.ru/"),
        _result(4, 2, "https://shared.ru/about"),
        _candidate(5, "https://shared.ru/", region=True, industry=25),
    ]
    assert replay_case_from_trace(
        events,
        gap_code="region_confirmation_missing",
        effective_regime="balanced",
        suggested_follow_up_query="first query",
    ) is None


def test_sparse_replay_does_not_need_candidate_quality_lineage():
    events = [
        _planned(1, 1, "first query"),
        _planned(2, 2, "second query"),
        _result(3, 1, "https://shared.ru/"),
        _result(4, 2, "https://shared.ru/about"),
        _candidate(5, "https://shared.ru/", region=True, industry=25),
    ]
    case = replay_case_from_trace(
        events,
        gap_code="sparse_yield",
        effective_regime="discovery",
        suggested_follow_up_query="first query",
        baseline_domains=[],
    )
    assert case is not None
    assert case.to_retained_outcome().evidence.added_unique_domains == 1


def test_trace_replay_rejects_gaps_not_provable_from_current_trace_contract():
    events = [_planned(1, 1, "query"), _result(2, 1, "https://example.ru/")]
    assert replay_case_from_trace(
        events,
        gap_code="duplicate_or_excluded_pressure",
        effective_regime="precision",
        suggested_follow_up_query="query",
    ) is None
    assert replay_case_from_trace(
        events,
        gap_code="discovery_novelty_unmeasured",
        effective_regime="discovery",
        suggested_follow_up_query="query",
    ) is None


def test_trace_replay_requires_one_exact_query_identity():
    events = [_planned(1, 1, "query one"), _result(2, 1, "https://example.ru/")]
    assert replay_case_from_trace(
        events,
        gap_code="sparse_yield",
        effective_regime="balanced",
        suggested_follow_up_query="different query",
    ) is None
