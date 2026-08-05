import sqlite3

import pytest

from app.logging_pressure_factory import (
    LoggingPressureRuntimeConfig,
    build_logging_pressure_runtime,
    logging_pressure_config_from_env,
)


def test_pressure_config_defaults_are_disabled() -> None:
    config = logging_pressure_config_from_env({})
    assert config.enabled is False
    assert config.interval_seconds == 60.0
    assert config.disk_path == "/app/data"
    assert config.recovery_samples == 3


def test_pressure_config_parses_explicit_environment() -> None:
    config = logging_pressure_config_from_env(
        {
            "AIMETON_LOGGING_PRESSURE_ENABLED": "true",
            "AIMETON_LOGGING_PRESSURE_INTERVAL_SECONDS": "30",
            "AIMETON_LOGGING_PRESSURE_DISK_PATH": "/tmp/data",
            "AIMETON_LOGGING_PRESSURE_RECOVERY_SAMPLES": "5",
        }
    )
    assert config.enabled is True
    assert config.interval_seconds == 30.0
    assert config.disk_path == "/tmp/data"
    assert config.recovery_samples == 5


def test_factory_builds_disabled_sampler_and_shared_audit_db(tmp_path) -> None:
    path = tmp_path / "runtime.sqlite3"
    runtime = build_logging_pressure_runtime(path)
    assert runtime.sampler.enabled is False
    assert runtime.sampler.running is False
    assert runtime.owner.status().mode.value == "full"
    with sqlite3.connect(path) as db:
        table = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='logging_pressure_transitions'"
        ).fetchone()
    assert table is not None


@pytest.mark.parametrize(
    "config",
    [
        LoggingPressureRuntimeConfig(interval_seconds=9),
        LoggingPressureRuntimeConfig(interval_seconds=3601),
        LoggingPressureRuntimeConfig(recovery_samples=0),
    ],
)
def test_factory_rejects_invalid_bounds(tmp_path, config) -> None:
    with pytest.raises(ValueError):
        build_logging_pressure_runtime(tmp_path / "runtime.sqlite3", config=config)
