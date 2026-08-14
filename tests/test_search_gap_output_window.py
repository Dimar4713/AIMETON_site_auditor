from app.models import HuntCandidate, HuntFunnel
from app.search_gap_shadow_refinement import observe_search_gaps


def candidate(*, region_confirmed=False, industry_match=0):
    return HuntCandidate(
        company_name="Example",
        url="https://example.com",
        source_title="Example",
        region_confirmed=region_confirmed,
        pre_score_factors={"industry_match": industry_match},
        qualification="test",
        business_summary="test",
        recommended_solution="test",
    )


def test_truncated_output_window_does_not_infer_region_or_industry_gap():
    gaps = observe_search_gaps(
        funnel=HuntFunnel(
            raw_results=30,
            unique_candidates=20,
            qualified_candidates=10,
            returned_candidates=1,
        ),
        effective_regime="balanced",
        candidates=[candidate()],
    )
    codes = {item.code for item in gaps}
    assert "region_confirmation_missing" not in codes
    assert "industry_confirmation_missing" not in codes


def test_complete_output_window_can_infer_region_and_industry_gap():
    gaps = observe_search_gaps(
        funnel=HuntFunnel(
            raw_results=10,
            unique_candidates=5,
            qualified_candidates=1,
            returned_candidates=1,
        ),
        effective_regime="balanced",
        candidates=[candidate()],
    )
    codes = {item.code for item in gaps}
    assert "region_confirmation_missing" in codes
    assert "industry_confirmation_missing" in codes
