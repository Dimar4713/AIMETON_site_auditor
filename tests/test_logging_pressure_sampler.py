from __future__ import annotations

import asyncio

import pytest

from app.logging_pressure import ResourceSnapshot
from app.logging_pressure_sampler import (
    LoggingPressureSampler,
    LoggingPressureSamplerConfig,
)


class _Owner:
    def __init__(self) -> None:
        self.snapshots: list[ResourceSnapshot] = []

    def evaluate(self, snapshot: ResourceSnapshot):
        self.snapshots.append(snapshot)


@pytest.mark.asyncio
async def test_disabled_sampler_does_not_start() -> None:
    owner = _Owner()
    sampler = LoggingPressureSampler(owner, ResourceSnapshot)
    await sampler.start()
    assert sampler.enabled is False
    assert sampler.running is False
    assert owner.snapshots == []


@pytest.mark.asyncio
async def test_sample_once_evaluates_one_snapshot() -> None:
    owner = _Owner()
    sampler = LoggingPressureSampler(owner, lambda: ResourceSnapshot(queue_depth=7))
    await sampler.sample_once()
    assert len(owner.snapshots) == 1
    assert owner.snapshots[0].queue_depth == 7


@pytest.mark.asyncio
async def test_sampler_is_fail_open_when_provider_raises() -> None:
    owner = _Owner()

    def fail():
        raise RuntimeError("metrics unavailable")

    sampler = LoggingPressureSampler(owner, fail)
    await sampler.sample_once()
    assert owner.snapshots == []


@pytest.mark.asyncio
async def test_enabled_sampler_starts_once_and_stops_cleanly() -> None:
    owner = _Owner()
    sampler = LoggingPressureSampler(
        owner,
        ResourceSnapshot,
        config=LoggingPressureSamplerConfig(enabled=True, interval_seconds=10),
    )
    await sampler.start()
    await sampler.start()
    await asyncio.sleep(0)
    assert sampler.running is True
    await sampler.stop()
    assert sampler.running is False
    assert len(owner.snapshots) <= 1


def test_sampler_interval_is_bounded() -> None:
    with pytest.raises(ValueError):
        LoggingPressureSamplerConfig(interval_seconds=9)
    with pytest.raises(ValueError):
        LoggingPressureSamplerConfig(interval_seconds=3601)
