from app.search_observer_llm import SearchObserverRecommendation
from app.search_observer_model_arena import (
    ModelArenaObservation,
    observation_from_recommendation,
    summarize_model_arena,
)
from app.search_observer_models import ObserverProvider, ResolvedObserverModel


def _model(name: str, provider: ObserverProvider, model: str) -> ResolvedObserverModel:
    return ResolvedObserverModel(
        profile_name=name,
        provider=provider,
        base_url="https://example.invalid/v1",
        api_key="secret",
        model=model,
        tier="O1",
        configured=True,
    )


def test_observation_keeps_shadow_invariant() -> None:
    recommendation = SearchObserverRecommendation(
        sufficient_evidence=True,
        summary="Enough evidence.",
        recommendations=[
            {
                "direction_index": 0,
                "action": "continue",
                "confidence": 0.9,
                "rationale": "Productive direction.",
            }
        ],
    )
    observation = observation_from_recommendation(
        scenario_slug="case-a",
        model=_model("qwen-flash", ObserverProvider.QWEN, "qwen-test"),
        latency_ms=120,
        recommendation=recommendation,
    )
    assert observation.schema_valid is True
    assert observation.routing_changed is False
    assert observation.action_counts == {"continue": 1}


def test_arena_ranks_schema_stability_before_latency() -> None:
    observations = [
        ModelArenaObservation(
            scenario_slug="a",
            profile_name="qwen-flash",
            provider="qwen",
            model="qwen-test",
            tier="O1",
            latency_ms=100,
            schema_valid=False,
            routing_changed=False,
            error_code="schema_invalid",
        ),
        ModelArenaObservation(
            scenario_slug="a",
            profile_name="glm-flash",
            provider="glm",
            model="glm-test",
            tier="O1",
            latency_ms=200,
            schema_valid=True,
            routing_changed=False,
            recommendation_count=1,
            action_counts={"continue": 1},
        ),
    ]
    summaries = summarize_model_arena(observations)
    assert [item.profile_name for item in summaries] == ["glm-flash", "qwen-flash"]


def test_arena_counts_cost_and_actions() -> None:
    observations = [
        ModelArenaObservation(
            scenario_slug="a",
            profile_name="deepseek-chat",
            provider="deepseek",
            model="deepseek-test",
            tier="O1",
            latency_ms=100,
            estimated_cost_usd=0.001,
            schema_valid=True,
            recommendation_count=2,
            action_counts={"refine": 2},
        ),
        ModelArenaObservation(
            scenario_slug="b",
            profile_name="deepseek-chat",
            provider="deepseek",
            model="deepseek-test",
            tier="O1",
            latency_ms=300,
            estimated_cost_usd=0.002,
            schema_valid=True,
            recommendation_count=1,
            action_counts={"continue": 1},
        ),
    ]
    summary = summarize_model_arena(observations)[0]
    assert summary.schema_success_rate == 1.0
    assert summary.mean_latency_ms == 200
    assert summary.total_estimated_cost_usd == 0.003
    assert summary.action_counts == {"refine": 2, "continue": 1}
