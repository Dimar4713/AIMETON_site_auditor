from decimal import Decimal

from app.search_observer import QueryYieldTelemetry, SearchWaveTelemetry
from app.search_observer_llm import (
    ObserverAction,
    SearchObserverRecommendation,
    _bounded_telemetry_payload,
)


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
