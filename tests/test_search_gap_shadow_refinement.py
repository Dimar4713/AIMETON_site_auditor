from app.models import HuntFunnel, HuntRequest
from app.search_gap_shadow_refinement import build_shadow_follow_up_queries, observe_search_gaps


def test_sparse_gap_and_discovery_gap_are_explicit():
    gaps = observe_search_gaps(funnel=HuntFunnel(raw_results=2, unique_candidates=1, qualified_candidates=0), effective_regime="discovery", candidates=[])
    codes = {item.code for item in gaps}
    assert "sparse_yield" in codes
    assert "discovery_novelty_unmeasured" in codes


def test_suggestions_are_bounded_deduped_and_non_steering():
    executed = "dentistry Krasnoyarsk контакты"
    plan = build_shadow_follow_up_queries(req=HuntRequest(region="Krasnoyarsk", industries=["dentistry"]), funnel=HuntFunnel(raw_results=2, unique_candidates=1, qualified_candidates=0), executed_queries=[executed], effective_regime="balanced", candidates=[], max_suggestions=2)
    assert len(plan.suggestions) <= 2
    assert all(item.query.casefold() != executed.casefold() for item in plan.suggestions)
    assert len({item.query.casefold() for item in plan.suggestions}) == len(plan.suggestions)
    assert plan.routing_changed is False
    assert plan.steering_enabled is False


def test_healthy_precision_wave_is_noop():
    plan = build_shadow_follow_up_queries(req=HuntRequest(region="Krasnoyarsk", industries=["dentistry"]), funnel=HuntFunnel(raw_results=20, unique_candidates=12, qualified_candidates=8, returned_candidates=5), executed_queries=[], effective_regime="precision", candidates=[], max_suggestions=2)
    assert plan.gaps == ()
    assert plan.suggestions == ()
