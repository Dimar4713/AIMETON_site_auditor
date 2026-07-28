from __future__ import annotations

import asyncio
import time
from copy import deepcopy
from dataclasses import dataclass

from app.search_gateway.models import SearchItem


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

