from decimal import Decimal

from app.search_gateway.models import (
    AttemptState,
    GatewayState,
    ProviderAttempt,
    SearchDiagnostics,
    SearchItem,
    SearchResponse,
)
from app.search_observer import build_search_wave_telemetry


def _response(*, provider: str, urls: list[str], latency_ms: int, cost: str = "0") -> SearchResponse:
    items = [
        SearchItem(url=url, title=url, snippet="", provider=provider)
        for url in urls
    ]
    return SearchResponse(
        results=items,
        diagnostics=SearchDiagnostics(
            state=GatewayState.SUCCESS,
            selected_provider=provider,
            attempts=[
                ProviderAttempt(
                    provider=provider,
                    state=AttemptState.SUCCEEDED,
                    request_fingerprint="sha256:" + "a" * 64,
                    latency_ms=latency_ms,
                    result_count=len(items),
                    cost_amount=Decimal(cost),
                    cost_currency="RUB",
                )
            ],
            total_cost_by_currency={"RUB": Decimal(cost)},
        ),
    )


def test_search_wave_telemetry_preserves_direction_order_and_yield() -> None:
    telemetry = build_search_wave_telemetry(
        ["official dentists", "dentistry catalog"],
        [
            _response(
                provider="yandex",
                urls=["https://a.example/", "https://b.example/"],
                latency_ms=120,
                cost="0.01",
            ),
            _response(
                provider="searxng",
                urls=["https://a.example/about", "https://a.example/contacts"],
                latency_ms=80,
            ),
        ],
    )

    assert telemetry.query_count == 2
    assert telemetry.result_count == 4
    assert telemetry.unique_domain_count == 2
    assert telemetry.duplicate_domain_ratio == 0.5
    assert telemetry.provider_result_counts == {"yandex": 2, "searxng": 2}
    assert telemetry.latency_ms_total == 200
    assert telemetry.total_cost_by_currency == {"RUB": Decimal("0.01")}
    assert [item.query for item in telemetry.directions] == [
        "official dentists",
        "dentistry catalog",
    ]
    assert telemetry.directions[0].unique_domain_count == 2
    assert telemetry.directions[1].unique_domain_count == 1
    assert telemetry.directions[1].duplicate_domain_ratio == 0.5


def test_search_wave_telemetry_is_observation_only() -> None:
    response = _response(
        provider="searxng",
        urls=["https://a.example/"],
        latency_ms=10,
    )

    before = response.model_dump()
    telemetry = build_search_wave_telemetry(["query"], [response])

    assert response.model_dump() == before
    assert telemetry.directions[0].query == "query"
