from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from app.search_gateway.cache import SQLiteSearchCache
from app.search_gateway.factory import _search_cache_from_env
from app.search_gateway.gateway import SearchGateway
from app.search_gateway.models import SearchItem, SearchPolicy, SearchRequest
from app.search_gateway.providers import SearchProvider


def _item(url: str = "https://example.org/") -> SearchItem:
    return SearchItem(
        url=url,
        title="Example",
        snippet="Persistent search evidence",
        provider="searxng",
    )


@pytest.mark.asyncio
async def test_sqlite_cache_survives_new_cache_instance(tmp_path: Path) -> None:
    path = tmp_path / "search-cache.sqlite3"
    first = SQLiteSearchCache(path)
    await first.set("key", [_item()], 900)

    second = SQLiteSearchCache(path)
    restored = await second.get("key")

    assert restored is not None
    assert len(restored) == 1
    assert str(restored[0].url) == "https://example.org/"
    assert restored[0].provider == "searxng"


@pytest.mark.asyncio
async def test_sqlite_cache_expires_using_wall_clock(tmp_path: Path) -> None:
    now = [1000.0]
    cache = SQLiteSearchCache(tmp_path / "search-cache.sqlite3", clock=lambda: now[0])
    await cache.set("key", [_item()], 10)
    assert await cache.get("key") is not None

    now[0] = 1010.0
    assert await cache.get("key") is None


@pytest.mark.asyncio
async def test_sqlite_cache_is_bounded(tmp_path: Path) -> None:
    now = [1000.0]
    cache = SQLiteSearchCache(
        tmp_path / "search-cache.sqlite3",
        max_entries=2,
        clock=lambda: now[0],
    )
    await cache.set("first", [_item("https://first.example/")], 30)
    now[0] += 1
    await cache.set("second", [_item("https://second.example/")], 40)
    now[0] += 1
    await cache.set("third", [_item("https://third.example/")], 50)

    assert await cache.get("first") is None
    assert await cache.get("second") is not None
    assert await cache.get("third") is not None


@pytest.mark.asyncio
async def test_corrupt_payload_raises_for_gateway_fail_open_handling(tmp_path: Path) -> None:
    path = tmp_path / "search-cache.sqlite3"
    cache = SQLiteSearchCache(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO search_cache(cache_key, expires_at, payload, updated_at) VALUES (?, ?, ?, ?)",
            ("broken", 9999999999.0, "not-json", 1.0),
        )

    with pytest.raises(Exception):
        await cache.get("broken")


class _BrokenCache:
    async def get(self, key: str):
        raise sqlite3.DatabaseError("synthetic broken cache")

    async def set(self, key: str, results: list[SearchItem], ttl_seconds: int) -> None:
        raise sqlite3.DatabaseError("synthetic broken cache")


class _Provider(SearchProvider):
    name = "searxng"
    paid = False
    cost_amount = Decimal("0")
    cost_currency = "USD"

    def __init__(self) -> None:
        self.calls = 0

    @property
    def configured(self) -> bool:
        return True

    async def search(self, request: SearchRequest, *, timeout_seconds: float) -> list[SearchItem]:
        self.calls += 1
        return [_item()]


@pytest.mark.asyncio
async def test_gateway_search_is_fail_open_when_cache_is_broken() -> None:
    provider = _Provider()
    gateway = SearchGateway([provider], cache=_BrokenCache())
    response = await gateway.search(
        SearchRequest(
            query="example company",
            limit=10,
            mission_id="mission-cache",
            correlation_id="corr-cache",
        ),
        SearchPolicy(
            provider_order=("searxng",),
            allowed_providers=frozenset({"searxng"}),
            retries=0,
            cache_ttl_seconds=900,
        ),
    )

    assert provider.calls == 1
    assert len(response.results) == 1
    assert response.diagnostics.cache_hit is False


def test_factory_selects_sqlite_cache_when_path_is_configured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "factory-cache.sqlite3"
    monkeypatch.setenv("SEARCH_CACHE_DB_PATH", str(path))
    monkeypatch.setenv("SEARCH_CACHE_MAX_ENTRIES", "777")

    cache = _search_cache_from_env()

    assert isinstance(cache, SQLiteSearchCache)
    assert cache.path == path


def test_stage_deploy_enables_cache_on_persistent_app_data() -> None:
    script = Path("scripts/deploy_stage.sh").read_text(encoding="utf-8")
    assert 'SEARCH_CACHE_DB_PATH: "/app/data/search-cache.sqlite3"' in script
    assert "./data/runtime-core:/app/data" in script
