from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from app.document_pipeline.models import FetchedDocument


@dataclass(frozen=True)
class _CacheEntry:
    value: FetchedDocument
    expires_at: float


class MemoryDocumentCache:
    def __init__(self) -> None:
        self._entries: dict[str, _CacheEntry] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> FetchedDocument | None:
        async with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at < time.monotonic():
                self._entries.pop(key, None)
                return None
            return entry.value.model_copy(deep=True)

    async def set(self, key: str, value: FetchedDocument, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        async with self._lock:
            self._entries[key] = _CacheEntry(
                value=value.model_copy(deep=True),
                expires_at=time.monotonic() + ttl_seconds,
            )
