from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from decimal import Decimal

from app.search_gateway.models import FallbackReason, SearchItem, SearchRequest
from app.search_gateway.providers import SearchProvider


SleepFn = Callable[[float], Awaitable[None]]
JitterFn = Callable[[float, float], float]


class ScheduledProvider(SearchProvider):
    """Apply provider-local concurrency and bounded jitter without changing search semantics.

    The wrapper deliberately does not hide origin, rotate identities, or retry on
    its own. SearchGateway keeps fallback/retry/circuit policy; this layer only
    smooths outbound pressure independently for each provider.

    Provider readiness/eligibility is part of search semantics and therefore
    MUST be delegated to the wrapped provider rather than falling back to the
    permissive base-class defaults.
    """

    def __init__(
        self,
        provider: SearchProvider,
        *,
        max_concurrency: int = 1,
        jitter_min_seconds: float = 0.0,
        jitter_max_seconds: float = 0.0,
        sleep: SleepFn = asyncio.sleep,
        jitter: JitterFn = random.uniform,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        if jitter_min_seconds < 0 or jitter_max_seconds < 0:
            raise ValueError("jitter must be non-negative")
        if jitter_max_seconds < jitter_min_seconds:
            raise ValueError("jitter_max_seconds must be >= jitter_min_seconds")
        self._provider = provider
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._jitter_min_seconds = jitter_min_seconds
        self._jitter_max_seconds = jitter_max_seconds
        self._sleep = sleep
        self._jitter = jitter
        self.max_concurrency = max_concurrency

    @property
    def name(self) -> str:
        return self._provider.name

    @property
    def paid(self) -> bool:
        return self._provider.paid

    @property
    def cost_amount(self) -> Decimal:
        return self._provider.cost_amount

    @property
    def cost_currency(self) -> str:
        return self._provider.cost_currency

    @property
    def configured(self) -> bool:
        return self._provider.configured

    @property
    def execution_allowed(self) -> bool:
        return self._provider.execution_allowed

    @property
    def execution_block_reason(self) -> FallbackReason | None:
        return self._provider.execution_block_reason

    async def search(
        self,
        request: SearchRequest,
        *,
        timeout_seconds: float,
    ) -> list[SearchItem]:
        async with self._semaphore:
            if self._jitter_max_seconds > 0:
                delay = self._jitter(
                    self._jitter_min_seconds,
                    self._jitter_max_seconds,
                )
                if delay > 0:
                    await self._sleep(delay)
            return await self._provider.search(
                request,
                timeout_seconds=timeout_seconds,
            )