from pathlib import Path

from app.hunter_lead_fit import lead_fit_rank
from app.models import HuntCandidate


DISCOVERY = Path("app/discovery.py")


def _candidate(*, lead_fit: str, score: int = 75) -> HuntCandidate:
    return HuntCandidate(
        company_name="Кандидат",
        url="https://example.ru/",
        source_title="Стоматология Красноярск",
        source_snippet="Лечение зубов",
        region_confirmed=True,
        preliminary_score=score,
        pre_score_status="calculated",
        pre_score_factors={"industry_match": 25, "region_match": 25},
        deep_analysis_performed=False,
        final_score=score,
        qualification="Перспективная",
        business_summary="",
        recommended_solution="",
        lead_fit=lead_fit,
        lead_fit_reason="test",
    )


def test_candidate_api_serializes_lead_fit_evidence() -> None:
    candidate = _candidate(lead_fit="commercial_candidate")
    candidate.lead_fit_evidence = ["private_phrase:частная стоматология"]
    payload = candidate.model_dump()
    assert payload["lead_fit"] == "commercial_candidate"
    assert payload["lead_fit_reason"] == "test"
    assert payload["lead_fit_evidence"] == ["private_phrase:частная стоматология"]


def test_lead_fit_priority_is_independent_from_score() -> None:
    commercial = _candidate(lead_fit="commercial_candidate", score=70)
    unknown = _candidate(lead_fit="unknown_candidate", score=95)
    institutional = _candidate(lead_fit="institutional_candidate", score=100)

    ordered = sorted(
        [institutional, unknown, commercial],
        key=lambda candidate: (lead_fit_rank(candidate.lead_fit), candidate.final_score or -1),
        reverse=True,
    )
    assert [candidate.lead_fit for candidate in ordered] == [
        "commercial_candidate",
        "unknown_candidate",
        "institutional_candidate",
    ]


def test_discovery_ranks_source_role_before_lead_fit_then_score() -> None:
    text = DISCOVERY.read_text(encoding="utf-8")
    sort_block = text.split("candidates.sort(", 1)[1].split("returned = candidates", 1)[0]
    role_position = sort_block.index("role_rank(_candidate_rank_role(candidate))")
    lead_fit_position = sort_block.index("lead_fit_rank(candidate.lead_fit)")
    final_score_position = sort_block.index("candidate.final_score")
    assert role_position < lead_fit_position < final_score_position


def test_returned_trace_exposes_lead_fit_and_reason() -> None:
    text = DISCOVERY.read_text(encoding="utf-8")
    returned_block = text.split('"candidate_returned"', 1)[1].split("else:", 1)[0]
    assert '"lead_fit": candidate.lead_fit' in returned_block
    assert '"lead_fit_reason": candidate.lead_fit_reason' in returned_block
    assert '"lead_fit_evidence": candidate.lead_fit_evidence' in returned_block
