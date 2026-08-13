from app.search_observer_scoring import (
    ObservedMarginalYield,
    SecondWaveShadowAction,
    assess_second_wave_shadow,
)


def outcome(**overrides):
    values = {
        "added_queries": 1,
        "added_raw_results": 20,
        "added_unique_domains": 8,
        "added_qualified_candidates": 5,
        "added_direct_or_official_candidates": 3,
        "duplicate_results": 1,
        "excluded_results": 1,
        "latency_ms": 1500,
        "cost_rub": 0.02,
    }
    values.update(overrides)
    return ObservedMarginalYield(**values)


def test_shadow_prefers_continue_for_clean_quality_gain():
    decision = assess_second_wave_shadow(outcome())
    assert decision.preferred_action == SecondWaveShadowAction.CONTINUE
    assert decision.would_run_second_wave is True
    assert decision.routing_changed is False


def test_shadow_prefers_refine_for_quality_gain_with_high_waste():
    decision = assess_second_wave_shadow(
        outcome(duplicate_results=7, excluded_results=7)
    )
    assert decision.waste_ratio == 0.7
    assert decision.preferred_action == SecondWaveShadowAction.REFINE
    assert decision.would_run_second_wave is True
    assert decision.routing_changed is False


def test_shadow_prefers_skip_without_quality_gain():
    decision = assess_second_wave_shadow(
        outcome(
            added_unique_domains=1,
            added_qualified_candidates=0,
            added_direct_or_official_candidates=0,
            duplicate_results=9,
            excluded_results=6,
        )
    )
    assert decision.preferred_action == SecondWaveShadowAction.SKIP
    assert decision.would_run_second_wave is False
    assert decision.routing_changed is False


def test_shadow_prefers_skip_when_no_later_wave_exists():
    decision = assess_second_wave_shadow(
        outcome(
            added_queries=0,
            added_raw_results=0,
            added_unique_domains=0,
            added_qualified_candidates=0,
            added_direct_or_official_candidates=0,
            duplicate_results=0,
            excluded_results=0,
            latency_ms=0,
            cost_rub=0.0,
        )
    )
    assert decision.preferred_action == SecondWaveShadowAction.SKIP
    assert decision.reason_code == "shadow_no_later_wave"
    assert decision.routing_changed is False
