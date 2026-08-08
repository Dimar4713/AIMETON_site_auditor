from types import SimpleNamespace

import pytest

from app.evidence_crawler.models import CrawlStatus
from app.mission_bounded_runtime import _collect_deep_site_evidence


@pytest.mark.asyncio
async def test_owned_evidence_includes_search_discovered_page_only_after_crawl(monkeypatch):
    seed_url = "https://example.org/"
    discovered_url = "https://example.org/ogrn/1234567890123"
    calls: list[tuple[str, str]] = []

    async def fake_fetch(raw: str):
        calls.append(("fetch", raw))
        if raw == seed_url:
            return {
                "final_url": seed_url,
                "title": "Example Company",
                "text": "seed evidence " * 120,
            }
        if raw == discovered_url:
            return {
                "final_url": discovered_url,
                "title": "ООО Example, ИНН 1234567890",
                "text": "verified registry profile evidence " * 120,
            }
        raise AssertionError(raw)

    async def fake_run_crawl(target_url: str, **kwargs):
        calls.append(("crawl", target_url))
        if target_url == seed_url:
            return SimpleNamespace(
                status=CrawlStatus.COMPLETED,
                pages=[SimpleNamespace(final_url=seed_url)],
                discovered_urls=[],
            )
        if target_url == discovered_url:
            return SimpleNamespace(
                status=CrawlStatus.COMPLETED,
                pages=[SimpleNamespace(final_url=discovered_url)],
                discovered_urls=[],
            )
        raise AssertionError(target_url)

    async def fake_discovery(*args, **kwargs):
        calls.append(("search", args[0]))
        return SimpleNamespace(urls=[discovered_url])

    monkeypatch.setattr("app.mission_bounded_runtime._fetch_preferred_target", fake_fetch)
    monkeypatch.setattr("app.mission_bounded_runtime._run_crawl", fake_run_crawl)
    monkeypatch.setattr("app.mission_bounded_runtime.discover_same_domain_urls", fake_discovery)

    seed, page_count, evidence = await _collect_deep_site_evidence(
        seed_url,
        owned_mission_id="mission-search-assisted",
    )

    assert seed["final_url"] == seed_url
    assert page_count == 2
    assert f"SOURCE: {discovered_url}" in evidence
    assert "verified registry profile evidence" in evidence
    assert calls.index(("search", seed_url)) < calls.index(("crawl", discovered_url))
    assert calls.index(("crawl", discovered_url)) < calls.index(("fetch", discovered_url))
