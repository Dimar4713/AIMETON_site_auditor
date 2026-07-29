from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

import httpx
import pytest

from app.document_pipeline import (
    Crawl4AIHttpWorker,
    DocumentPipeline,
    DocumentRequest,
    DynamicFetcher,
    FetchPath,
    FetchPolicy,
    RawDocument,
    StaticHttpFetcher,
)
from app.scraper import FetchError


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "sef" / "document-fetch-5-v0.1.json"
ENCODING_FIXTURES = ROOT / "tests" / "fixtures" / "input-stabilization-encodings.json"


def request(url: str = "https://example.test/about") -> DocumentRequest:
    return DocumentRequest(
        mission_id="mission_doc_test",
        source_id="source_doc_test",
        correlation_id="corr_doc_test",
        url=url,
    )


class FakeDynamicFetcher(DynamicFetcher):
    def __init__(
        self,
        name: str,
        *,
        html: str | None = None,
        error: Exception | None = None,
        configured: bool = True,
    ) -> None:
        self.name = name
        self.html = html
        self.error = error
        self._configured = configured
        self.calls = 0

    @property
    def configured(self) -> bool:
        return self._configured

    async def fetch(self, url: str, *, timeout_seconds: float) -> RawDocument:
        del timeout_seconds
        self.calls += 1
        if self.error:
            raise self.error
        assert self.html is not None
        return RawDocument(
            final_url=url,
            title="Динамический документ",
            html=self.html,
            media_type="text/html",
            path=self.name,
        )


def rich_html(label: str = "Подтверждённый факт") -> str:
    return (
        "<html><head><title>Документ</title></head><body><main>"
        f"<h1>{label}</h1>"
        "<p>Первичный документ содержит проверяемую информацию о компании, "
        "её услугах, реквизитах и способах связи с клиентами.</p>"
        "<table><tr><th>ИНН</th><td>2400000000</td></tr></table>"
        '<a href="/contacts">Контакты</a>'
        "</main></body></html>"
    )


@pytest.fixture(autouse=True)
def public_url_guard(monkeypatch):
    monkeypatch.setattr(
        "app.document_pipeline.fetchers._validate_public_url",
        lambda _url: None,
    )


@pytest.mark.asyncio
async def test_static_document_has_digests_locators_tables_links_and_cache():
    calls = 0

    def handler(request_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=rich_html(),
        )

    pipeline = DocumentPipeline(
        static_fetcher=StaticHttpFetcher(transport=httpx.MockTransport(handler)),
    )
    first = await pipeline.fetch(request())
    second = await pipeline.fetch(request())

    assert first.document.content_digest == first.normalized_content_digest
    assert first.raw_content_digest.startswith("sha256:")
    assert first.normalized_content_digest.startswith("sha256:")
    assert first.raw_content_digest != first.normalized_content_digest
    assert first.document.accessed_at
    assert first.diagnostics.path == FetchPath.STATIC
    assert first.tables[0].rows == [["ИНН", "2400000000"]]
    assert str(first.links[0].url) == "https://example.test/contacts"
    assert any(block.locator == "body/p[1]" for block in first.blocks)
    assert second.document.id == first.document.id
    assert second.diagnostics.path == FetchPath.CACHE
    assert second.diagnostics.cache_hit is True
    assert calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    json.loads(ENCODING_FIXTURES.read_text(encoding="utf-8"))["cases"],
    ids=lambda case: case["id"],
)
async def test_encoding_chain_preserves_russian_text(case):
    content = base64.b64decode(case["body_base64"])
    pipeline = DocumentPipeline(
        static_fetcher=StaticHttpFetcher(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    headers={"content-type": case["content_type"]},
                    content=content,
                )
            )
        ),
    )

    fetched = await pipeline.fetch(request(), FetchPolicy(min_text_length=20))

    assert case["expected_text"] in fetched.normalized_text
    assert fetched.diagnostics.encoding_source == case["expected_encoding_source"]
    assert fetched.diagnostics.detected_encoding
    assert fetched.diagnostics.raw_bytes == len(content)


@pytest.mark.asyncio
async def test_undetermined_encoding_is_an_explicit_fail_closed_error():
    fetcher = StaticHttpFetcher(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                headers={"content-type": "text/html"},
                content=b"\x00\x01\x02\x03" * 100,
            )
        )
    )

    with pytest.raises(FetchError, match="encoding_undetermined"):
        await fetcher.fetch(
            "https://example.test/",
            timeout_seconds=1,
            max_bytes=1_024,
            max_redirects=1,
        )


@pytest.mark.asyncio
async def test_multiple_semantic_areas_header_footer_redirect_and_canonical_are_preserved():
    html = """
    <html>
      <head>
        <title>Группа компаний</title>
        <link rel="canonical" href="https://www.example.test:443/company">
      </head>
      <body>
        <header><p>Телефон +7 391 111-22-33</p></header>
        <main><h1>Первая область</h1><p>Основное юридическое лицо ООО Альфа.</p></main>
        <article><h2>Вторая область</h2><p>Бренд Бета и производственная площадка.</p></article>
        <footer><p>ИНН 2400000000, адрес Красноярск.</p></footer>
      </body>
    </html>
    """

    def handler(incoming: httpx.Request) -> httpx.Response:
        if incoming.url.host == "example.test":
            return httpx.Response(
                301,
                headers={"location": "https://www.example.test/landing"},
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=html,
        )

    pipeline = DocumentPipeline(
        static_fetcher=StaticHttpFetcher(transport=httpx.MockTransport(handler)),
    )
    fetched = await pipeline.fetch(request("https://example.test/start"))

    assert "Первая область" in fetched.normalized_text
    assert "Вторая область" in fetched.normalized_text
    assert [block.text for block in fetched.header_blocks] == [
        "Телефон +7 391 111-22-33"
    ]
    assert [block.text for block in fetched.footer_blocks] == [
        "ИНН 2400000000, адрес Красноярск."
    ]
    assert str(fetched.document.url) == "https://www.example.test/landing"
    assert str(fetched.declared_canonical_url) == "https://www.example.test/company"
    assert fetched.canonical_same_origin is True
    assert len(fetched.diagnostics.redirect_history) == 1
    hop = fetched.diagnostics.redirect_history[0]
    assert hop.from_origin == "https://example.test"
    assert hop.to_origin == "https://www.example.test"
    assert "start" not in hop.model_dump_json()


@pytest.mark.asyncio
async def test_tilda_bitrix_style_fixture_keeps_all_sections_and_requisites():
    html = (ROOT / "tests" / "fixtures" / "cms-multi-area.html").read_text(
        encoding="utf-8"
    )
    pipeline = DocumentPipeline(
        static_fetcher=StaticHttpFetcher(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    headers={"content-type": "text/html; charset=utf-8"},
                    text=html,
                )
            )
        ),
    )

    fetched = await pipeline.fetch(request("https://cms.example/"))

    for expected in (
        "Производство строительных конструкций",
        "Технологии и оборудование",
        "ООО «Пример», ИНН 2400000000.",
    ):
        assert expected in fetched.normalized_text
    assert fetched.header_blocks[0].text.startswith("Отдел продаж")
    assert fetched.footer_blocks[0].text.startswith("660000")


@pytest.mark.asyncio
async def test_thin_static_document_uses_crawl4ai_before_browser():
    static = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><body><div id='root'>Загрузка</div></body></html>",
        )
    )
    crawl4ai = FakeDynamicFetcher("crawl4ai", html=rich_html())
    browser = FakeDynamicFetcher("browser", html=rich_html())
    pipeline = DocumentPipeline(
        static_fetcher=StaticHttpFetcher(transport=static),
        crawl4ai=crawl4ai,
        browser=browser,
    )

    result = await pipeline.fetch(request())

    assert result.diagnostics.path == FetchPath.CRAWL4AI
    assert result.diagnostics.fallback_used is True
    assert crawl4ai.calls == 1
    assert browser.calls == 0


@pytest.mark.asyncio
async def test_worker_failure_isolated_and_browser_fallback_is_bounded():
    static = httpx.MockTransport(
        lambda _request: httpx.Response(
            403,
            headers={"content-type": "text/html"},
            text="",
        )
    )
    crawl4ai = FakeDynamicFetcher(
        "crawl4ai",
        error=FetchError("worker crashed"),
    )
    browser = FakeDynamicFetcher("browser", html=rich_html())
    pipeline = DocumentPipeline(
        static_fetcher=StaticHttpFetcher(transport=static),
        crawl4ai=crawl4ai,
        browser=browser,
    )

    result = await pipeline.fetch(request())

    assert result.diagnostics.path == FetchPath.BROWSER
    assert crawl4ai.calls == 1
    assert browser.calls == 1


@pytest.mark.asyncio
async def test_crawl4ai_adapter_uses_official_self_hosted_contract_without_token_leak():
    observed: dict = {}

    def handler(request_: httpx.Request) -> httpx.Response:
        observed["authorization"] = request_.headers.get("authorization")
        observed["payload"] = json.loads(request_.content)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "success": True,
                        "url": "https://example.test/about",
                        "cleaned_html": rich_html(),
                        "metadata": {"title": "Документ"},
                    }
                ]
            },
        )

    worker = Crawl4AIHttpWorker(
        "http://crawl4ai:11235",
        api_token="secret-token",
        transport=httpx.MockTransport(handler),
    )
    result = await worker.fetch(
        "https://example.test/about",
        timeout_seconds=5,
    )

    assert observed["authorization"] == "Bearer secret-token"
    assert observed["payload"]["urls"] == ["https://example.test/about"]
    assert observed["payload"]["browser_config"]["type"] == "BrowserConfig"
    assert observed["payload"]["crawler_config"]["type"] == "CrawlerRunConfig"
    assert result.path == "crawl4ai"
    assert "secret-token" not in repr(result)


@pytest.mark.asyncio
async def test_private_redirect_is_fail_closed_without_dynamic_bypass(monkeypatch):
    def guard(url: str) -> None:
        if "127.0.0.1" in url:
            raise FetchError("Доступ к локальным и служебным адресам запрещён")

    monkeypatch.setattr(
        "app.document_pipeline.fetchers._validate_public_url",
        guard,
    )

    def handler(request_: httpx.Request) -> httpx.Response:
        assert request_.url.host == "public.example"
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})

    dynamic = FakeDynamicFetcher("browser", html=rich_html())
    pipeline = DocumentPipeline(
        static_fetcher=StaticHttpFetcher(transport=httpx.MockTransport(handler)),
        browser=dynamic,
    )

    with pytest.raises(FetchError, match="локальным"):
        await pipeline.fetch(request("https://public.example/"))
    assert dynamic.calls == 0


@pytest.mark.asyncio
async def test_document_size_limit_is_fail_closed():
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"x" * 2_048,
        )
    )
    pipeline = DocumentPipeline(
        static_fetcher=StaticHttpFetcher(transport=transport),
    )
    policy = FetchPolicy(max_bytes=1_024)

    with pytest.raises(FetchError, match="размер"):
        await pipeline.fetch(request(), policy)


@pytest.mark.asyncio
async def test_promotion_requires_quote_at_exact_locator_not_search_snippet():
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text=rich_html("Юридическое лицо ООО «ПРИМЕР»"),
        )
    )
    pipeline = DocumentPipeline(
        static_fetcher=StaticHttpFetcher(transport=transport),
    )
    fetched = await pipeline.fetch(request())
    promoted = pipeline.promote_quote(
        fetched,
        locator="body/h1[1]",
        quote="ООО «ПРИМЕР»",
    )

    assert promoted.evidence.document_id == fetched.document.id
    assert promoted.evidence.locator == "body/h1[1]"
    assert promoted.evidence.digest.startswith("sha256:")

    with pytest.raises(ValueError, match="not present"):
        pipeline.promote_quote(
            fetched,
            locator="body/h1[1]",
            quote="Поисковый сниппет с неподтверждённой выручкой",
        )


@pytest.mark.asyncio
async def test_concurrency_is_limited_to_two():
    active = 0
    maximum = 0

    class SlowStaticFetcher(StaticHttpFetcher):
        async def fetch(self, url, *, timeout_seconds, max_bytes, max_redirects):
            nonlocal active, maximum
            del timeout_seconds, max_bytes, max_redirects
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0.01)
            active -= 1
            return RawDocument(
                final_url=url,
                title="Документ",
                html=rich_html(),
                media_type="text/html",
                path="static",
            )

    pipeline = DocumentPipeline(
        static_fetcher=SlowStaticFetcher(),
        max_concurrency=2,
    )
    await asyncio.gather(
        *[
            pipeline.fetch(request(f"https://example.test/{index}"))
            for index in range(5)
        ]
    )
    assert maximum == 2


@pytest.mark.asyncio
async def test_document_fetch_benchmark_5_meets_success_gate():
    benchmark = json.loads(BENCHMARK.read_text(encoding="utf-8"))
    cases = {case["url"]: case for case in benchmark["cases"]}

    def handler(request_: httpx.Request) -> httpx.Response:
        case = cases[str(request_.url)]
        html = (ROOT / case["fixture"]).read_text(encoding="utf-8")
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text=html,
        )

    pipeline = DocumentPipeline(
        static_fetcher=StaticHttpFetcher(transport=httpx.MockTransport(handler)),
    )
    successes = 0
    for case in benchmark["cases"]:
        result = await pipeline.fetch(request(case["url"]))
        if case["required_text"] in result.normalized_text:
            successes += 1
        assert result.document.content_digest
        assert result.document.accessed_at

    success_rate = successes / len(benchmark["cases"])
    assert success_rate >= benchmark["minimum_success_rate"]
