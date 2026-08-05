from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
import shutil

from app.logging_pressure import ResourceSnapshot


def _memory_percent_from_meminfo(text: str) -> float:
    values: dict[str, int] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        parts = raw.strip().split()
        if not parts:
            continue
        try:
            values[key] = int(parts[0])
        except ValueError:
            continue
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", 0)
    if total <= 0:
        raise ValueError("MemTotal unavailable")
    used = max(0, total - available)
    return min(100.0, max(0.0, used * 100.0 / total))


def _cpu_percent_from_load(load_1m: float, cpu_count: int | None) -> float:
    cores = max(1, cpu_count or 1)
    return min(100.0, max(0.0, load_1m * 100.0 / cores))


class LinuxResourceSnapshotProvider:
    """Dependency-free bounded host snapshot for the logging pressure controller."""

    def __init__(
        self,
        *,
        disk_path: str | Path = "/app/data",
        queue_depth: Callable[[], int] | None = None,
        write_p95_ms: Callable[[], float] | None = None,
        meminfo_reader: Callable[[], str] | None = None,
        load_reader: Callable[[], float] | None = None,
        cpu_count_reader: Callable[[], int | None] | None = None,
    ) -> None:
        self.disk_path = Path(disk_path)
        self.queue_depth = queue_depth or (lambda: 0)
        self.write_p95_ms = write_p95_ms or (lambda: 0.0)
        self.meminfo_reader = meminfo_reader or (
            lambda: Path("/proc/meminfo").read_text(encoding="utf-8")
        )
        self.load_reader = load_reader or (lambda: os.getloadavg()[0])
        self.cpu_count_reader = cpu_count_reader or os.cpu_count

    def __call__(self) -> ResourceSnapshot:
        try:
            usage = shutil.disk_usage(self.disk_path)
            disk_free_percent = usage.free * 100.0 / usage.total if usage.total else 0.0
            storage_failed = False
        except OSError:
            disk_free_percent = 0.0
            storage_failed = True

        try:
            memory_percent = _memory_percent_from_meminfo(self.meminfo_reader())
        except (OSError, ValueError):
            memory_percent = 0.0

        try:
            cpu_percent = _cpu_percent_from_load(
                self.load_reader(),
                self.cpu_count_reader(),
            )
        except (OSError, ValueError):
            cpu_percent = 0.0

        return ResourceSnapshot(
            queue_depth=max(0, int(self.queue_depth())),
            write_p95_ms=max(0.0, float(self.write_p95_ms())),
            disk_free_percent=disk_free_percent,
            memory_percent=memory_percent,
            cpu_percent=cpu_percent,
            storage_failed=storage_failed,
        )
