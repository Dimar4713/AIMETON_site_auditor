import asyncio
from decimal import Decimal

from app.search_observer import QueryYieldTelemetry, SearchWaveTelemetry
from app.search_observer_llm import (
    DEFAULT_SEARCH_OBSERVER_MODEL,
    DEFAULT_SEARCH_OBSERVER_TIMEOUT_SECONDS,
    ObserverAction,
    SearchObserverRecommendation,
    _bounded_telemetry_payload,
    _legacy_model,
    _observer_timeout_seconds,
    evaluate_search_wave_shadow,
    get_last_shadow_observer_evidence,
    shadow_observer_runtime_descriptor,
)
from app.search_observer_models import ResolvedObserverModel


def _telemetry() -> SearchWaveTelemetry:
    return SearchWaveTelemetry(
        query_count=2,
        result_count=15,
        unique_domain_count=10,
        duplicate_domain_ratio=0.333333,
        provider_result_counts={"searxng": 8, "yandex": 7},
        attempt_states={"succeeded": 4},
        latency_ms_total=420,
        degraded_attempts=0,
        total_cost_by_currency={"RUB": Decimal("0.02")},
        directions=[
            QueryYieldTelemetry(
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
            ),
            QueryYieldTelemetry(
                query="каталог стоматологий Красноярска",
                result_count=5,
                unique_domain_count=2,
                duplicate_domain_ratio=0.6,
                provider_result_counts={"searxng": 3, "yandex": 2},
                attempt_states={"succeeded": 2},
                latency_ms_total=200,
                degraded_attempts=0,
                cache_hit=False,
                total_cost_by_currency={"RUB": Decimal("0.01")},
            ),
        ],
    )


def test_shadow_recommendation_cannot_claim_routing_change() -> None:
    recommendation = SearchObserverRecommendation(
        sufficient_evidence=True,
        summary="Официальные сайты дают лучшую уникальную отдачу.",
        recommendations=[
            {
                "direction_index": 0,
                "action": ObserverAction.BOOST,
                "confidence": 0.9,
                "rationale": "Высокая доля уникальных доменов.",
            }
        ],
    )

    assert recommendation.observer_mode == "shadow"
    assert recommendation.routing_changed is False


def test_bounded_payload_preserves_direction_evidence() -> None:
    payload = _bounded_telemetry_payload(_telemetry())

    assert payload["query_count"] == 2
    assert payload["total_cost_by_currency"] == {"RUB": "0.02"}
    assert len(payload["directions"]) == 2
    assert payload["directions"][0]["unique_domain_count"] == 8
    assert payload["directions"][1]["duplicate_domain_ratio"] == 0.6


def test_shadow_observer_uses_dedicated_default_model(monkeypatch) -> None:
    monkeypatch.setenv("ROUTERAI_API_KEY", "secret")
    monkeypatch.delenv("HUNTER_SEARCH_OBSERVER_MODEL", raising=False)

    model = _legacy_model()

    assert model is not None
    assert model.model == DEFAULT_SEARCH_OBSERVER_MODEL
    assert model.profile_name == "routerai-shadow-observer"
    assert model.tier == "O1"


def test_shadow_observer_model_can_be_overridden(monkeypatch) -> None:
    monkeypatch.setenv("ROUTERAI_API_KEY", "secret")
    monkeypatch.setenv("HUNTER_SEARCH_OBSERVER_MODEL", "qwen/qwen3.5-9b")

    model = _legacy_model()

    assert model is not None
    assert model.model == "qwen/qwen3.5-9b"


def test_shadow_observer_runtime_descriptor_exposes_no_secret(monkeypatch) -> None:
    monkeypatch.setenv("ROUTERAI_API_KEY", "do-not-leak")
    monkeypatch.setenv("HUNTER_SEARCH_OBSERVER_MODEL", "deepseek/deepseek-v3.2")
    monkeypatch.setenv("HUNTER_SEARCH_OBSERVER_TIMEOUT_SECONDS", "12")

    descriptor = shadow_observer_runtime_descriptor()

    assert descriptor == {
        "profile_name": "routerai-shadow-observer",
        "provider": "routerai",
        "model": "deepseek/deepseek-v3.2",
        "tier": "O1",
        "configured": True,
        "timeout_seconds": 12.0,
    }
    assert "api_key" not in descriptor
    assert "base_url" not in descriptor
    assert "do-not-leak" not in str(descriptor)


def test_shadow_observer_timeout_is_bounded(monkeypatch) -> None:
    monkeypatch.delenv("HUNTER_SEARCH_OBSERVER_TIMEOUT_SECONDS", raising=False)
    assert _observer_timeout_seconds() == DEFAULT_SEARCH_OBSERVER_TIMEOUT_SECONDS

    monkeypatch.setenv("HUNTER_SEARCH_OBSERVER_TIMEOUT_SECONDS", "invalid")
    assert _observer_timeout_seconds() == DEFAULT_SEARCH_OBSERVER_TIMEOUT_SECONDS

    monkeypatch.setenv("HUNTER_SEARCH_OBSERVER_TIMEOUT_SECONDS", "-5")
    assert _observer_timeout_seconds() == 1.0

    monkeypatch.setenv("HUNTER_SEARCH_OBSERVER_TIMEOUT_SECONDS", "99")
    assert _observer_timeout_seconds() == 30.0

    monkeypatch.setenv("HUNTER_SEARCH_OBSERVER_TIMEOUT_SECONDS", "12.5")
    assert _observer_timeout_seconds() == 12.5


def test_shadow_observer_timeout_fails_open_and_records_evidence(monkeypatch) -> None:
    from app import search_observer_llm as observer

    model = ResolvedObserverModel(
        profile_name="test-shadow",
        provider="routerai",
        base_url="https://example.test/v1",
        api_key="secret",
        model="test/model",
        tier="O1",
        configured=True,
    )

    async def slow_evaluator(telemetry, resolved_model):
        await asyncio.sleep(0.05)
        raise AssertionError("wall-clock guard should fire first")

    monkeypatch.setattr(observer, "_legacy_model", lambda: model)
    monkeypatch.setattr(
        observer,
        "shadow_observer_runtime_descriptor",
        lambda: {
            "profile_name": "test-shadow",
            "provider": "routerai",
            "model": "test/model",
            "tier": "O1",
            "configured": True,
            "timeout_seconds": 0.01,
        },
    )
    monkeypatch.setattr(observer, "_observer_timeout_seconds", lambda: 0.01)
    monkeypatch.setattr(observer, "evaluate_search_wave_shadow_with_model", slow_evaluator)

    async def exercise():
        recommendation = await evaluate_search_wave_shadow(_telemetry())
        return recommendation, get_last_shadow_observer_evidence()

    recommendation, evidence = asyncio.run(exercise())
    assert recommendation is None
    assert evidence["observer_outcome"] == "timeout"
    assert evidence["schema_valid"] is False
    assert evidence["observer_recommendation_count"] == 0
    assert evidence["model"] == "test/model"
    assert evidence["observer_latency_ms"] >= 9
