import asyncio

import pytest

from app.retention_runner import RetentionPeriodicRunner, RetentionRunnerConfig


class Owner:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.calls: list[tuple[str, ...]] = []

    def run_once(self, *, protected_mission_ids=()):
        self.calls.append(tuple(protected_mission_ids))
        if self.fail:
            raise RuntimeError("cleanup unavailable")


@pytest.mark.asyncio
async def test_disabled_runner_does_not_start():
    owner = Owner()
    runner = RetentionPeriodicRunner(
        owner,
        config=RetentionRunnerConfig(enabled=False, interval_seconds=60),
    )

    await runner.start()
    await asyncio.sleep(0)
    await runner.stop()

    assert owner.calls == []


@pytest.mark.asyncio
async def test_enabled_runner_runs_and_forwards_protected_missions():
    owner = Owner()
    runner = RetentionPeriodicRunner(
        owner,
        config=RetentionRunnerConfig(enabled=True, interval_seconds=60),
        protected_mission_ids=lambda: {"mission-active"},
    )

    await runner.start()
    for _ in range(20):
        if owner.calls:
            break
        await asyncio.sleep(0.01)
    await runner.stop()

    assert owner.calls == [("mission-active",)]


@pytest.mark.asyncio
async def test_runner_is_fail_open_and_stoppable():
    owner = Owner(fail=True)
    runner = RetentionPeriodicRunner(
        owner,
        config=RetentionRunnerConfig(enabled=True, interval_seconds=60),
    )

    await runner.start()
    for _ in range(20):
        if owner.calls:
            break
        await asyncio.sleep(0.01)
    await runner.stop()

    assert len(owner.calls) == 1


def test_interval_is_bounded():
    with pytest.raises(ValueError, match="between 60 and 86400"):
        RetentionRunnerConfig(enabled=True, interval_seconds=0)
