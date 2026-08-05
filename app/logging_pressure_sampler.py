from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

from app.logging_pressure import ResourceSnapshot
from app.logging_pressure_runtime import LoggingPressureRuntimeOwner


@dataclass(frozen=True)
class LoggingPressureSamplerConfig:
    enabled: bool = False
    interval_seconds: float = 60.0

    def __post_init__(self) -> None:
        if self.interval_seconds < 10 or self.interval_seconds > 3600:
            raise ValueError("interval_seconds must be between 10 and 3600")


class LoggingPressureSampler:
    """Bounded fail-open periodic sampler; disabled unless explicitly enabled."""

    def __init__(
        self,
        owner: LoggingPressureRuntimeOwner,
        snapshot_provider: Callable[[], ResourceSnapshot],
        *,
        config: LoggingPressureSamplerConfig | None = None,
    ) -> None:
        self.owner = owner
        self.snapshot_provider = snapshot_provider
        self.config = config or LoggingPressureSamplerConfig()
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if not self.enabled or self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(
            self._run(),
            name="aimeton-logging-pressure-sampler",
        )

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

    async def sample_once(self) -> None:
        try:
            snapshot = await asyncio.to_thread(self.snapshot_provider)
            await asyncio.to_thread(self.owner.evaluate, snapshot)
        except Exception:
            # Resource protection must not become a product-traffic failure source.
            return

    async def _run(self) -> None:
        while not self._stop.is_set():
            await self.sample_once()
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self.config.interval_seconds,
                )
            except TimeoutError:
                continue
