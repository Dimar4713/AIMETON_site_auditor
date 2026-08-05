import pytest

from app.logging_pressure import (
    LoggingMode,
    LoggingPressureController,
    PressurePolicy,
    PressureReason,
    ResourceSnapshot,
)


def test_storage_failure_immediately_disables_primary_writes() -> None:
    controller = LoggingPressureController()
    transition = controller.evaluate(ResourceSnapshot(storage_failed=True))
    assert transition.current_mode is LoggingMode.WRITE_DISABLED
    assert transition.reason is PressureReason.STORAGE_FAILURE
    assert transition.changed is True


@pytest.mark.parametrize(
    ("snapshot", "expected_mode", "expected_reason"),
    [
        (ResourceSnapshot(queue_depth=5_000), LoggingMode.THROTTLED, PressureReason.QUEUE_PRESSURE),
        (ResourceSnapshot(write_p95_ms=100), LoggingMode.THROTTLED, PressureReason.WRITE_LATENCY),
        (ResourceSnapshot(queue_depth=20_000), LoggingMode.MINIMAL, PressureReason.QUEUE_PRESSURE),
        (ResourceSnapshot(disk_free_percent=9), LoggingMode.MINIMAL, PressureReason.DISK_PRESSURE),
        (ResourceSnapshot(disk_free_percent=4), LoggingMode.EMERGENCY_ONLY, PressureReason.DISK_PRESSURE),
        (ResourceSnapshot(memory_percent=90), LoggingMode.EMERGENCY_ONLY, PressureReason.MEMORY_PRESSURE),
        (ResourceSnapshot(cpu_percent=95), LoggingMode.EMERGENCY_ONLY, PressureReason.CPU_PRESSURE),
    ],
)
def test_pressure_thresholds_select_expected_mode(snapshot, expected_mode, expected_reason) -> None:
    transition = LoggingPressureController().evaluate(snapshot)
    assert transition.current_mode is expected_mode
    assert transition.reason is expected_reason


def test_recovery_requires_stable_samples_and_moves_one_step_only() -> None:
    controller = LoggingPressureController(
        policy=PressurePolicy(recovery_samples=3),
        initial_mode=LoggingMode.EMERGENCY_ONLY,
    )
    safe = ResourceSnapshot()
    first = controller.evaluate(safe)
    second = controller.evaluate(safe)
    third = controller.evaluate(safe)
    assert first.changed is False and first.recovery_samples == 1
    assert second.changed is False and second.recovery_samples == 2
    assert third.changed is True
    assert third.current_mode is LoggingMode.MINIMAL
    assert third.reason is PressureReason.RECOVERY_STABLE


def test_unstable_sample_resets_recovery_hysteresis() -> None:
    controller = LoggingPressureController(
        policy=PressurePolicy(recovery_samples=2),
        initial_mode=LoggingMode.MINIMAL,
    )
    assert controller.evaluate(ResourceSnapshot()).recovery_samples == 1
    held = controller.evaluate(ResourceSnapshot(memory_percent=85))
    assert held.changed is False
    assert held.current_mode is LoggingMode.MINIMAL
    assert held.recovery_samples == 0
    assert controller.evaluate(ResourceSnapshot()).recovery_samples == 1


def test_pressure_never_improves_mode_without_recovery_guard() -> None:
    controller = LoggingPressureController(initial_mode=LoggingMode.WRITE_DISABLED)
    transition = controller.evaluate(ResourceSnapshot(disk_free_percent=12, memory_percent=85))
    assert transition.current_mode is LoggingMode.WRITE_DISABLED
    assert transition.changed is False


def test_invalid_thresholds_fail_closed() -> None:
    with pytest.raises(ValueError):
        PressurePolicy(throttled_queue_depth=10, minimal_queue_depth=10)
    with pytest.raises(ValueError):
        PressurePolicy(emergency_disk_free_percent=10, minimal_disk_free_percent=10)
    with pytest.raises(ValueError):
        PressurePolicy(recovery_samples=0)
    with pytest.raises(ValueError):
        ResourceSnapshot(queue_depth=-1)
