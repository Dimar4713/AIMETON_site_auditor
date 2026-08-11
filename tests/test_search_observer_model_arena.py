from decimal import Decimal

import pytest

from app.search_observer import QueryYieldTelemetry, SearchWaveTelemetry
from app.search_observer_llm import SearchObserverRecommendation
from app.search_observer_model_arena import (
    ModelArenaCase,
    ModelArenaObservation,
    evaluate_model_arena_case,
    observation_from_recommendation,
    summarize_model_arena,
    validate_replay_case,
)
from app.search_observer_models import ObserverProvider, ResolvedObserverModel


def _model(name: str, provider: ObserverProvider, model: str, configured: bool = True) -> ResolvedObserverModel:
    return ResolvedObserverModel(
        profile_name=name,
        provider=provider,
        base_url="https://example.invalid/v1" if configured else "",
        api_key="secret" if configured else "",
        model=model if configured else "",
        tier="O1",
        configured=configured,
    )


def _telemetry() -> SearchWaveTelemetry:
    direction = QueryYieldTelemetry(
        query="стоматология Красноярск официальный сайт",
        result_count=10,
        unique_domain_count=8,
        duplicate_domain_ratio=0.2,
        provider_result_counts={"searxng": 5, "yandex": 5},
        attempt_states={"succeeded": 2},
        latency_ms_total=220,
        degraded_attempts=0,
        cache_hit=False,
        total_cost_by_currency={"RUB": Decimal("0.01")},
    )
    return SearchWaveTelemetry(
        query_count=1,
        result_count=10,
        unique_domain_count=8,
        duplicate_domain_ratio=0.2,
        provider_result_counts={"searxng": 5, "yandex": 5},
        attempt_states={"succeeded": 2},
        latency_ms_total=220,
        degraded_attempts=0,
        total_cost_by_currency={"RUB": Decimal("0.01")},
        directions=[direction],
    )


def test_observation_keeps_shadow_invariant() -> None:
    recommendation = SearchObserverRecommendation(
        sufficient_evidence=True,
        summary="Enough evidence.",
        recommendations=[
            {"direction_index": 0, "action": "continue", "confidence": 0.9, "rationale": "Productive direction."}
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


def test_replay_case_requires_full_direction_telemetry() -> None:
    broken = _telemetry().model_copy(update={"query_count": 2})
    with pytest.raises(ValueError, match="direction_count_mismatch"):
        validate_replay_case(ModelArenaCase(scenario_slug="broken", telemetry=broken))


@pytest.mark.asyncio
async def test_unconfigured_model_does_not_call_evaluator() -> None:
    called = False

    async def evaluator(telemetry, model):
        nonlocal called
        called = True
        return None

    result = await evaluate_model_arena_case(
        case=ModelArenaCase(scenario_slug="case-a", telemetry=_telemetry()),
        model=_model("qwen-flash", ObserverProvider.QWEN, "qwen-test", configured=False),
        evaluator=evaluator,
    )
    assert called is False
    assert result.configured is False
    assert result.error_code == "model_not_configured"
    assert result.routing_changed is False


@pytest.mark.asyncio
async def test_arena_evaluation_is_advisory_only() -> None:
    async def evaluator(telemetry, model):
        return SearchObserverRecommendation(
            sufficient_evidence=True,
            summary="Enough evidence.",
            recommendations=[
                {"direction_index": 0, "action": "continue", "confidence": 0.9, "rationale": "Productive direction."}
            ],
        )

    result = await evaluate_model_arena_case(
        case=ModelArenaCase(scenario_slug="case-a", telemetry=_telemetry()),
        model=_model("qwen-flash", ObserverProvider.QWEN, "qwen-test"),
        evaluator=evaluator,
    )
    assert result.schema_valid is True
    assert result.routing_changed is False
    assert result.action_counts == {"continue": 1}


def test_arena_ranks_schema_stability_before_latency() -> None:
    observations = [
        ModelArenaObservation(
            scenario_slug="a", profile_name="qwen-flash", provider="qwen", model="qwen-test", tier="O1",
            latency_ms=100, schema_valid=False, routing_changed=False, error_code="schema_invalid",
        ),
        ModelArenaObservation(
            scenario_slug="a", profile_name="glm-flash", provider="glm", model="glm-test", tier="O1",
            latency_ms=200, schema_valid=True, routing_changed=False, recommendation_count=1,
            action_counts={"continue": 1},
        ),
    ]
    summaries = summarize_model_arena(observations)
    assert [item.profile_name for item in summaries] == ["glm-flash", "qwen-flash"]


def test_arena_counts_cost_and_actions() -> None:
    observations = [
        ModelArenaObservation(
            scenario_slug="a", profile_name="deepseek-chat", provider="deepseek", model="deepseek-test", tier="O1",
            latency_ms=100, estimated_cost_usd=0.001, schema_valid=True, recommendation_count=2,
            action_counts={"refine": 2},
        ),
        ModelArenaObservation(
            scenario_slug="b", profile_name="deepseek-chat", provider="deepseek", model="deepseek-test", tier="O1",
            latency_ms=300, estimated_cost_usd=0.002, schema_valid=True, recommendation_count=1,
            action_counts={"continue": 1},
        ),
    ]
    summary = summarize_model_arena(observations)[0]
    assert summary.schema_success_rate == 1.0
    assert summary.mean_latency_ms == 200
    assert summary.total_estimated_cost_usd == 0.003
    assert summary.action_counts == {"refine": 2, "continue": 1}
