from pathlib import Path
from types import SimpleNamespace

import pytest

import app.linux_resource_snapshot as linux_snapshot
from app.linux_resource_snapshot import (
    LinuxResourceSnapshotProvider,
    _cpu_percent_from_load,
    _memory_percent_from_meminfo,
)


def test_memory_percent_uses_memavailable() -> None:
    text = "MemTotal: 1000 kB\nMemAvailable: 250 kB\n"
    assert _memory_percent_from_meminfo(text) == 75.0


def test_memory_percent_rejects_missing_total() -> None:
    with pytest.raises(ValueError):
        _memory_percent_from_meminfo("MemAvailable: 10 kB\n")


def test_cpu_percent_is_normalized_by_core_count() -> None:
    assert _cpu_percent_from_load(2.0, 4) == 50.0
    assert _cpu_percent_from_load(8.0, 4) == 100.0


def test_provider_builds_bounded_snapshot(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        linux_snapshot.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(total=1000, used=700, free=300),
    )
    provider = LinuxResourceSnapshotProvider(
        disk_path=tmp_path,
        queue_depth=lambda: 42,
        write_p95_ms=lambda: 12.5,
        meminfo_reader=lambda: "MemTotal: 1000 kB\nMemAvailable: 400 kB\n",
        load_reader=lambda: 1.0,
        cpu_count_reader=lambda: 4,
    )
    snapshot = provider()
    assert snapshot.queue_depth == 42
    assert snapshot.write_p95_ms == 12.5
    assert snapshot.disk_free_percent == 30.0
    assert snapshot.memory_percent == 60.0
    assert snapshot.cpu_percent == 25.0
    assert snapshot.storage_failed is False


def test_disk_failure_sets_storage_failed_without_raising(monkeypatch, tmp_path) -> None:
    def fail(path):
        raise OSError("unavailable")

    monkeypatch.setattr(linux_snapshot.shutil, "disk_usage", fail)
    provider = LinuxResourceSnapshotProvider(
        disk_path=tmp_path,
        meminfo_reader=lambda: "MemTotal: 1000 kB\nMemAvailable: 1000 kB\n",
        load_reader=lambda: 0.0,
        cpu_count_reader=lambda: 1,
    )
    snapshot = provider()
    assert snapshot.storage_failed is True
    assert snapshot.disk_free_percent == 0.0
