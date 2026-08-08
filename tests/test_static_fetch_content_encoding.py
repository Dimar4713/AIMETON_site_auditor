from __future__ import annotations

import gzip

import httpx
import pytest

from app.document_pipeline import StaticHttpFetcher


@pytest.fixture(autouse=True)
def public_url_guard(monkeypatch):
    monkeypatch.setattr(
        "app.document_pipeline.fetchers._validate_public_url",
        lambda _url: None,
    )


@pytest.mark.asyncio
async def test_static_fetcher_advertises_only_runtime_supported_encodings_and_decodes_gzip():
    html = (
        "<!doctype html><html><head><title>Репутация</title></head>"
        "<body><main><h1>ООО Пример</h1><p>ИНН 1650000000</p></main></body></html>"
    ).encode("utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["accept-encoding"] == "gzip, deflate"
        assert "br" not in request.headers["accept-encoding"]
        return httpx.Response(
            200,
            headers={
                "content-type": "text/html; charset=utf-8",
                "content-encoding": "gzip",
            },
            content=gzip.compress(html),
        )

    fetched = await StaticHttpFetcher(
        transport=httpx.MockTransport(handler)
    ).fetch(
        "https://example.test/company",
        timeout_seconds=1,
        max_bytes=10_000,
        max_redirects=1,
        allowed_hosts=frozenset({"example.test"}),
    )

    assert fetched.html.startswith("<!doctype html>")
    assert "ИНН 1650000000" in fetched.html
    assert fetched.raw_content == html
    assert fetched.detected_encoding == "utf-8"
    assert fetched.encoding_source == "http"
