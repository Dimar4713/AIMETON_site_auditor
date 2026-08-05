from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from app.retention_service import RetentionLifecycleOwner


@dataclass(frozen=True)
class RetentionRunnerConfig:
    enabled: bool = False
    interval_seconds: float = 3600.0

    def __post_init__(self) -> None:
        if self.interval_seconds < 60 or self.interval_seconds > 86400:
            raise ValueError("interval_seconds must be between 60 and 86400")


class RetentionPeriodicRunner:
    """Config-gated fail-open periodic runner owned by the application lifespan."""

    def __init__(
        self,
        owner: RetentionLifecycleOwner,
        *,
        config: RetentionRunnerConfig,
        protected_mission_ids: Callable[[], Iterable[str]] | None = None,
    ) -> None:
        self.owner = owner
        self.config = config
        self._protected_mission_ids = protected_mission_ids or (lambda: ())
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @property
    def enabled(self) -> bool:
        """Safe status projection for lifecycle and admin diagnostics."""
        return self.config.enabled

    @property
    def interval_seconds(self) -> float:
        """Configured cadence without exposing mutable runner internals."""
        return self.config.interval_seconds

    @property
    def running(self) -> bool:
        """Whether the background task is currently owned by the lifespan."""
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if not self.config.enabled or self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="aimeton-retention-runner")

    async def stop(self) -> None:
        task = self._task
        if task is None:
            return
        self._stop.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.to_thread(
                    self.owner.run_once,
                    protected_mission_ids=tuple(self._protected_mission_ids()),
                )
            except Exception:
                # Observability and cleanup must remain fail-open for product traffic.
                pass
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.config.interval_seconds)
            except TimeoutError:
                continue
