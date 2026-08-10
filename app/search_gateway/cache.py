from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.search_gateway.models import SearchItem


class SearchCache(Protocol):
    async def get(self, key: str) -> list[SearchItem] | None: ...

    async def set(self, key: str, results: list[SearchItem], ttl_seconds: int) -> None: ...


@dataclass
class _Entry:
    expires_at: float
    results: list[SearchItem]


class MemorySearchCache:
    """Bounded process-local TTL cache behind a replaceable cache contract."""

    def __init__(self, max_entries: int = 2048) -> None:
        self._max_entries = max_entries
        self._entries: dict[str, _Entry] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> list[SearchItem] | None:
        async with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= time.monotonic():
                self._entries.pop(key, None)
                return None
            return deepcopy(entry.results)

    async def set(self, key: str, results: list[SearchItem], ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        async with self._lock:
            if len(self._entries) >= self._max_entries:
                oldest = min(self._entries, key=lambda item: self._entries[item].expires_at)
                self._entries.pop(oldest, None)
            self._entries[key] = _Entry(
                expires_at=time.monotonic() + ttl_seconds,
                results=deepcopy(results),
            )


class SQLiteSearchCache:
    """Persistent bounded TTL cache using only Python's sqlite3 runtime.

    The file may live on AIMETON's persistent `/app/data` mount, so completed
    search results survive container recreation and can be shared by processes
    that use the same local volume. SearchGateway treats cache failures as
    fail-open; this backend is an optimization, never a search dependency.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        max_entries: int = 4096,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._max_entries = max_entries
        self._clock = clock
        self._lock = asyncio.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS search_cache (
                    cache_key TEXT PRIMARY KEY,
                    expires_at REAL NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_search_cache_expires_at ON search_cache(expires_at)"
            )

    def _get_sync(self, key: str) -> list[SearchItem] | None:
        now = self._clock()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT expires_at, payload FROM search_cache WHERE cache_key = ?",
                (key,),
            ).fetchone()
            if row is None:
                return None
            expires_at, payload = row
            if float(expires_at) <= now:
                connection.execute("DELETE FROM search_cache WHERE cache_key = ?", (key,))
                return None
        decoded = json.loads(str(payload))
        if not isinstance(decoded, list):
            raise ValueError("search cache payload must be a list")
        return [SearchItem.model_validate(item) for item in decoded]

    async def get(self, key: str) -> list[SearchItem] | None:
        async with self._lock:
            return await asyncio.to_thread(self._get_sync, key)

    def _set_sync(self, key: str, results: list[SearchItem], ttl_seconds: int) -> None:
        now = self._clock()
        expires_at = now + ttl_seconds
        payload = json.dumps(
            [item.model_dump(mode="json") for item in results],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        with self._connect() as connection:
            connection.execute("DELETE FROM search_cache WHERE expires_at <= ?", (now,))
            connection.execute(
                """
                INSERT INTO search_cache(cache_key, expires_at, payload, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    expires_at = excluded.expires_at,
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (key, expires_at, payload, now),
            )
            count = int(connection.execute("SELECT COUNT(*) FROM search_cache").fetchone()[0])
            excess = max(0, count - self._max_entries)
            if excess:
                connection.execute(
                    """
                    DELETE FROM search_cache
                    WHERE cache_key IN (
                        SELECT cache_key FROM search_cache
                        ORDER BY expires_at ASC, updated_at ASC
                        LIMIT ?
                    )
                    """,
                    (excess,),
                )

    async def set(self, key: str, results: list[SearchItem], ttl_seconds: int) -> None:
        if ttl_seconds <= 0 or not results:
            return
        async with self._lock:
            await asyncio.to_thread(self._set_sync, key, results, ttl_seconds)
