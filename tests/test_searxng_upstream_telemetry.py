from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from app.search_gateway.models import FallbackReason, SearchRequest
from app.search_gateway.upstream_telemetry import (
    ScheduledProvider,
    SearxngProvider,
    TracedSearchGateway,
)


def _request(query: str, suffix: str) -> SearchRequest:
    return SearchRequest(
        query=query,
        limit=10,
        language="ru-RU",
        mission_id="telemetry-test",
        correlation_id=f"telemetry-{suffix}",
    )


def test_searxng_engine_telemetry_is_process_lifetime_and_health_is_zero_call(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        outbound_engines: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            outbound_engines.append(request.url.params.get("engines", ""))
            if len(outbound_engines) == 1:
                return httpx.Response(
                    200,
                    json={
                        "results": [
                            {
                                "url": "https://example.test/one",
                                "title": "one",
                                "content": "one",
                            }
                        ],
                        "unresponsive_engines": [
                            ["duckduckgo", "CAPTCHA required"],
                            ["unknown-engine", "CAPTCHA required"],
                        ],
                    },
                )
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "url": "https://example.test/two",
                            "title": "two",
                            "content": "two",
                        }
                    ],
                    "unresponsive_engines": [],
                },
            )

        provider = SearxngProvider(
            "https://searxng.test",
            engines=("duckduckgo", "bing"),
            engine_fanout=2,
            engine_block_cooldown_seconds=300,
            clock=lambda: 1000.0,
            transport=httpx.MockTransport(handler),
        )
        scheduled = ScheduledProvider(
            provider,
            max_concurrency=2,
            jitter_min_seconds=0.0,
            jitter_max_seconds=0.0,
        )
        gateway = TracedSearchGateway(
            [scheduled],
            trace_db_path=tmp_path / "trace.sqlite3",
        )

        await scheduled.search(_request("dentistry one", "one"), timeout_seconds=1.0)
        await scheduled.search(_request("dentistry two", "two"), timeout_seconds=1.0)

        assert outbound_engines == ["duckduckgo,bing", "bing"]

        health_before = gateway.health()
        health_after = gateway.health()
        assert len(outbound_engines) == 2
        assert health_before == health_after

        searxng = health_before[0]
        payload = searxng.model_dump(mode="json", exclude_none=True)
        telemetry = payload["upstream_telemetry"]
        assert telemetry == [
            {
                "upstream": "duckduckgo",
                "selected_requests": 1,
                "degradation_events": 1,
                "degradation_rate": 1.0,
                "last_degradation_reason": FallbackReason.CAPTCHA.value,
                "scope": "process_lifetime",
            },
            {
                "upstream": "bing",
                "selected_requests": 2,
                "degradation_events": 0,
                "degradation_rate": 0.0,
                "scope": "process_lifetime",
            },
        ]
        assert all(row["upstream"] != "unknown-engine" for row in telemetry)

    asyncio.run(scenario())


def test_degradation_is_counted_even_when_cooldown_is_disabled() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "url": "https://example.test/result",
                            "title": "result",
                            "content": "result",
                        }
                    ],
                    "unresponsive_engines": [["duckduckgo", "CAPTCHA required"]],
                },
            )

        provider = SearxngProvider(
            "https://searxng.test",
            engines=("duckduckgo",),
            engine_fanout=1,
            engine_block_cooldown_seconds=0,
            transport=httpx.MockTransport(handler),
        )
        await provider.search(_request("dentistry", "no-cooldown"), timeout_seconds=1.0)
        row = provider.upstream_telemetry()[0]
        assert row.selected_requests == 1
        assert row.degradation_events == 1
        assert row.degradation_rate == 1.0
        assert row.last_degradation_reason is FallbackReason.CAPTCHA
        assert provider.upstream_cooldowns() == []

    asyncio.run(scenario())
