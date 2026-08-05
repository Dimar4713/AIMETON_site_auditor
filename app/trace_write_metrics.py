from __future__ import annotations

from collections import deque
from pathlib import Path
from statistics import quantiles
from threading import RLock
from time import perf_counter
from typing import Callable

from app.trace_ledger import SQLiteTraceLedger, TraceEvent, TraceEventCreate


class TraceWriteMetrics:
    """Bounded process-local metrics for trace write pressure.

    Metrics contain only counters and timings. They never retain trace payloads,
    mission identifiers, provider data or secrets. The registry is intentionally
    process-local: durable evidence remains in the transition audit ledger.
    """

    def __init__(self, *, latency_window: int = 256) -> None:
        if latency_window < 20 or latency_window > 4096:
            raise ValueError("latency_window must be between 20 and 4096")
        self._lock = RLock()
        self._pending = 0
        self._latencies_ms: deque[float] = deque(maxlen=latency_window)

    def begin(self) -> None:
        with self._lock:
            self._pending += 1

    def finish(self, elapsed_ms: float) -> None:
        with self._lock:
            self._pending = max(0, self._pending - 1)
            self._latencies_ms.append(max(0.0, float(elapsed_ms)))

    def queue_depth(self) -> int:
        with self._lock:
            return self._pending

    def write_p95_ms(self) -> float:
        with self._lock:
            samples = tuple(self._latencies_ms)
        if not samples:
            return 0.0
        if len(samples) < 20:
            return max(samples)
        return float(quantiles(samples, n=100, method="inclusive")[94])


_REGISTRY_LOCK = RLock()
_REGISTRY: dict[str, TraceWriteMetrics] = {}


def trace_write_metrics_for(path: str | Path) -> TraceWriteMetrics:
    key = str(Path(path).expanduser().resolve(strict=False))
    with _REGISTRY_LOCK:
        return _REGISTRY.setdefault(key, TraceWriteMetrics())


class InstrumentedSQLiteTraceLedger(SQLiteTraceLedger):
    """SQLite trace ledger that records only bounded write-pressure metrics."""

    def __init__(self, path: str | Path) -> None:
        self.write_metrics = trace_write_metrics_for(path)
        super().__init__(path)

    def append(self, request: TraceEventCreate) -> TraceEvent:
        started = perf_counter()
        self.write_metrics.begin()
        try:
            return super().append(request)
        finally:
            self.write_metrics.finish((perf_counter() - started) * 1000.0)


def trace_pressure_callbacks(path: str | Path) -> tuple[Callable[[], int], Callable[[], float]]:
    metrics = trace_write_metrics_for(path)
    return metrics.queue_depth, metrics.write_p95_ms
