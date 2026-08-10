from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.search_gateway.cache import SQLiteSearchCache
from app.search_gateway.models import SearchItem


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
