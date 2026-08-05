from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LoggingMode(str, Enum):
    FULL = "full"
    THROTTLED = "throttled"
    MINIMAL = "minimal"
    EMERGENCY_ONLY = "emergency_only"
    WRITE_DISABLED = "write_disabled"


class PressureReason(str, Enum):
    NONE = "none"
    QUEUE_PRESSURE = "queue_pressure"
    WRITE_LATENCY = "write_latency"
    DISK_PRESSURE = "disk_pressure"
    MEMORY_PRESSURE = "memory_pressure"
    CPU_PRESSURE = "cpu_pressure"
    STORAGE_FAILURE = "storage_failure"
    RECOVERY_STABLE = "recovery_stable"


@dataclass(frozen=True)
class ResourceSnapshot:
    queue_depth: int = 0
    write_p95_ms: float = 0.0
    disk_free_percent: float = 100.0
    memory_percent: float = 0.0
    cpu_percent: float = 0.0
    storage_failed: bool = False

    def __post_init__(self) -> None:
        if self.queue_depth < 0:
            raise ValueError("queue_depth must be non-negative")
        for name, value in (
            ("write_p95_ms", self.write_p95_ms),
            ("disk_free_percent", self.disk_free_percent),
            ("memory_percent", self.memory_percent),
            ("cpu_percent", self.cpu_percent),
        ):
            if value < 0:
                raise ValueError(f"{name} must be non-negative")


@dataclass(frozen=True)
class PressurePolicy:
    throttled_queue_depth: int = 5_000
    throttled_write_p95_ms: float = 100.0
    minimal_queue_depth: int = 20_000
    minimal_disk_free_percent: float = 10.0
    emergency_disk_free_percent: float = 5.0
    emergency_memory_percent: float = 90.0
    emergency_cpu_percent: float = 95.0
    recovery_queue_depth: int = 1_000
    recovery_write_p95_ms: float = 50.0
    recovery_disk_free_percent: float = 15.0
    recovery_memory_percent: float = 80.0
    recovery_cpu_percent: float = 80.0
    recovery_samples: int = 3

    def __post_init__(self) -> None:
        if self.recovery_samples < 1:
            raise ValueError("recovery_samples must be positive")
        if self.throttled_queue_depth < 1 or self.minimal_queue_depth <= self.throttled_queue_depth:
            raise ValueError("queue thresholds must be increasing")
        if not 0 < self.emergency_disk_free_percent < self.minimal_disk_free_percent:
            raise ValueError("disk thresholds must be ordered")


@dataclass(frozen=True)
class ModeTransition:
    previous_mode: LoggingMode
    current_mode: LoggingMode
    reason: PressureReason
    changed: bool
    recovery_samples: int


_MODE_ORDER = (
    LoggingMode.FULL,
    LoggingMode.THROTTLED,
    LoggingMode.MINIMAL,
    LoggingMode.EMERGENCY_ONLY,
    LoggingMode.WRITE_DISABLED,
)


class LoggingPressureController:
    """Deterministic logging degradation controller with one-step recovery hysteresis."""

    def __init__(
        self,
        *,
        policy: PressurePolicy | None = None,
        initial_mode: LoggingMode = LoggingMode.FULL,
    ) -> None:
        self.policy = policy or PressurePolicy()
        self.mode = initial_mode
        self._recovery_samples = 0

    def evaluate(self, snapshot: ResourceSnapshot) -> ModeTransition:
        previous = self.mode
        target, reason = self._pressure_target(snapshot)
        if _MODE_ORDER.index(target) > _MODE_ORDER.index(self.mode):
            self.mode = target
            self._recovery_samples = 0
            return ModeTransition(previous, self.mode, reason, True, 0)

        if target is self.mode:
            self._recovery_samples = 0
            return ModeTransition(previous, self.mode, reason, False, 0)

        if not self._is_recovery_safe(snapshot):
            self._recovery_samples = 0
            return ModeTransition(previous, self.mode, PressureReason.NONE, False, 0)

        self._recovery_samples += 1
        if self._recovery_samples < self.policy.recovery_samples:
            return ModeTransition(
                previous,
                self.mode,
                PressureReason.NONE,
                False,
                self._recovery_samples,
            )

        current_index = _MODE_ORDER.index(self.mode)
        self.mode = _MODE_ORDER[max(0, current_index - 1)]
        self._recovery_samples = 0
        return ModeTransition(
            previous,
            self.mode,
            PressureReason.RECOVERY_STABLE,
            True,
            0,
        )

    def _pressure_target(
        self,
        snapshot: ResourceSnapshot,
    ) -> tuple[LoggingMode, PressureReason]:
        p = self.policy
        if snapshot.storage_failed:
            return LoggingMode.WRITE_DISABLED, PressureReason.STORAGE_FAILURE
        if snapshot.disk_free_percent < p.emergency_disk_free_percent:
            return LoggingMode.EMERGENCY_ONLY, PressureReason.DISK_PRESSURE
        if snapshot.memory_percent >= p.emergency_memory_percent:
            return LoggingMode.EMERGENCY_ONLY, PressureReason.MEMORY_PRESSURE
        if snapshot.cpu_percent >= p.emergency_cpu_percent:
            return LoggingMode.EMERGENCY_ONLY, PressureReason.CPU_PRESSURE
        if snapshot.queue_depth >= p.minimal_queue_depth:
            return LoggingMode.MINIMAL, PressureReason.QUEUE_PRESSURE
        if snapshot.disk_free_percent < p.minimal_disk_free_percent:
            return LoggingMode.MINIMAL, PressureReason.DISK_PRESSURE
        if snapshot.queue_depth >= p.throttled_queue_depth:
            return LoggingMode.THROTTLED, PressureReason.QUEUE_PRESSURE
        if snapshot.write_p95_ms >= p.throttled_write_p95_ms:
            return LoggingMode.THROTTLED, PressureReason.WRITE_LATENCY
        return LoggingMode.FULL, PressureReason.NONE

    def _is_recovery_safe(self, snapshot: ResourceSnapshot) -> bool:
        p = self.policy
        return (
            not snapshot.storage_failed
            and snapshot.queue_depth <= p.recovery_queue_depth
            and snapshot.write_p95_ms <= p.recovery_write_p95_ms
            and snapshot.disk_free_percent >= p.recovery_disk_free_percent
            and snapshot.memory_percent <= p.recovery_memory_percent
            and snapshot.cpu_percent <= p.recovery_cpu_percent
        )
