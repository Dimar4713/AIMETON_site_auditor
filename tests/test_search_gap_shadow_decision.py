from app.search_gap_shadow_decision import decide_shadow_second_wave
from app.search_gap_shadow_refinement import (
    FollowUpQuerySuggestion,
    SearchGapObservation,
    ShadowRefinementPlan,
)


def _gap(code: str) -> SearchGapObservation:
    return SearchGapObservation(code=code, evidence_target="target", reason="reason")


def _suggestion(code: str) -> FollowUpQuerySuggestion:
    return FollowUpQuerySuggestion(
        query="стоматология Красноярск контакты",
        reason_code=code,
        evidence_target="target",
    )


def test_shadow_decision_continues_for_unresolved_gap_with_bounded_follow_up():
    plan = ShadowRefinementPlan(
        gaps=(_gap("sparse_yield"),),
        suggestions=(_suggestion("sparse_yield"),),
    )
    decision = decide_shadow_second_wave(plan)
    assert decision.action == "continue"
    assert decision.reason_code == "shadow_continue_unresolved_gap_with_bounded_follow_up"
    assert decision.routing_changed is False
    assert decision.steering_enabled is False
    assert decision.promotion_activated is False


def test_shadow_decision_refines_when_duplicate_pressure_is_present():
    plan = ShadowRefinementPlan(
        gaps=(_gap("sparse_yield"), _gap("duplicate_or_excluded_pressure")),
        suggestions=(_suggestion("duplicate_or_excluded_pressure"),),
    )
    decision = decide_shadow_second_wave(plan)
    assert decision.action == "refine"
    assert decision.reason_code == "shadow_refine_duplicate_or_excluded_pressure"
    assert decision.gap_count == 2
    assert decision.suggestion_count == 1


def test_shadow_decision_skips_when_no_bounded_follow_up_exists():
    plan = ShadowRefinementPlan(gaps=(_gap("sparse_yield"),), suggestions=())
    decision = decide_shadow_second_wave(plan)
    assert decision.action == "skip"
    assert decision.reason_code == "shadow_no_bounded_follow_up_available"
    assert decision.suggestion_count == 0


def test_shadow_decision_skips_clean_complete_wave_without_gaps():
    decision = decide_shadow_second_wave(ShadowRefinementPlan(gaps=(), suggestions=()))
    assert decision.action == "skip"
    assert decision.gap_count == 0
    assert decision.routing_changed is False
