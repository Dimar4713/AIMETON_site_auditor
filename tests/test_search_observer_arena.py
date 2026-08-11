from decimal import Decimal

import pytest

from app.search_observer import QueryYieldTelemetry, SearchWaveTelemetry
from app.search_observer_arena import ArenaCase, evaluate_case, summarize_arena, validate_replay_case
from app.search_observer_llm import SearchObserverRecommendation
from app.search_observer_models import ObserverProvider, ResolvedObserverModel


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


def _model(configured: bool = True) -> ResolvedObserverModel:
    return ResolvedObserverModel(
        profile_name="qwen-flash",
        provider=ObserverProvider.QWEN,
        base_url="https://example.invalid/v1" if configured else "",
        api_key="secret" if configured else "",
        model="qwen-test" if configured else "",
        tier="O1",
        configured=configured,
    )


def test_replay_case_requires_full_direction_telemetry() -> None:
    broken = _telemetry().model_copy(update={"query_count": 2})
    with pytest.raises(ValueError, match="direction_count_mismatch"):
        validate_replay_case(ArenaCase(case_id="broken", telemetry=broken))


@pytest.mark.asyncio
async def test_unconfigured_model_does_not_call_evaluator() -> None:
    called = False

    async def evaluator(telemetry, model):
        nonlocal called
        called = True
        return None

    result = await evaluate_case(ArenaCase(case_id="c1", telemetry=_telemetry()), _model(False), evaluator)
    assert called is False
    assert result.error_code == "model_not_configured"
    assert result.routing_changed is False


@pytest.mark.asyncio
async def test_model_arena_records_advisory_result_only() -> None:
    async def evaluator(telemetry, model):
        return SearchObserverRecommendation(
            sufficient_evidence=True,
            summary="Высокая уникальная отдача.",
            recommendations=[
                {
                    "direction_index": 0,
                    "action": "continue",
                    "confidence": 0.9,
                    "rationale": "Направление продуктивно.",
                }
            ],
        )

    result = await evaluate_case(ArenaCase(case_id="c1", telemetry=_telemetry()), _model(True), evaluator)
    assert result.schema_valid is True
    assert result.routing_changed is False
    assert result.actions == {"continue": 1}


def test_arena_summary_reports_schema_rate_and_routing_invariant() -> None:
    from app.search_observer_arena import ArenaResult

    summary = summarize_arena([
        ArenaResult(case_id="a", profile_name="qwen", provider="qwen", model="m", configured=True, latency_ms=10, schema_valid=True),
        ArenaResult(case_id="b", profile_name="qwen", provider="qwen", model="m", configured=True, latency_ms=20, schema_valid=False),
    ])
    assert summary == [{
        "profile_name": "qwen",
        "case_count": 2,
        "configured_count": 2,
        "schema_valid_count": 1,
        "schema_valid_rate": 0.5,
        "mean_latency_ms": 10.0,
        "routing_changed_count": 0,
    }]
