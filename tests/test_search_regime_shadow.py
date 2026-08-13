from app.search_regime_shadow import resolve_auto_search_regime


def test_auto_regime_uses_discovery_for_sparse_funnel():
    decision = resolve_auto_search_regime(
        raw_results=3,
        unique_candidates=2,
        qualified_candidates=1,
        duplicate_results=0,
        excluded_results=0,
    )
    assert decision.effective == "discovery"
    assert decision.reason == "rarity_or_sparsity"
    assert decision.routing_changed is False
    assert decision.steering_enabled is False


def test_auto_regime_uses_precision_for_high_waste_pressure():
    decision = resolve_auto_search_regime(
        raw_results=20,
        unique_candidates=8,
        qualified_candidates=4,
        duplicate_results=6,
        excluded_results=4,
    )
    assert decision.effective == "precision"
    assert decision.reason == "duplicate_or_excluded_pressure"


def test_auto_regime_uses_precision_for_sufficient_quality():
    decision = resolve_auto_search_regime(
        raw_results=30,
        unique_candidates=15,
        qualified_candidates=10,
        duplicate_results=2,
        excluded_results=1,
    )
    assert decision.effective == "precision"
    assert decision.reason == "sufficient_high_quality_candidates"


def test_auto_regime_defaults_to_balanced():
    decision = resolve_auto_search_regime(
        raw_results=20,
        unique_candidates=10,
        qualified_candidates=4,
        duplicate_results=2,
        excluded_results=1,
    )
    assert decision.effective == "balanced"
    assert decision.reason == "balanced_default"
