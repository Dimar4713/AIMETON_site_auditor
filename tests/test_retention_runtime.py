from pathlib import Path

import pytest

from app.retention_runtime import (
    RetentionRuntimeConfig,
    build_retention_runner,
    retention_runtime_config_from_env,
)


def test_retention_runtime_is_disabled_by_default():
    config = retention_runtime_config_from_env({})

    assert config.enabled is False
    assert config.interval_seconds == 3600.0
    assert config.batch_size == 1000
    assert config.max_batches == 10
    assert config.max_runtime_seconds == 2.0


def test_retention_runtime_reads_explicit_bounded_configuration():
    config = retention_runtime_config_from_env(
        {
            "AIMETON_RETENTION_ENABLED": "true",
            "AIMETON_RETENTION_INTERVAL_SECONDS": "900",
            "AIMETON_RETENTION_BATCH_SIZE": "250",
            "AIMETON_RETENTION_MAX_BATCHES": "4",
            "AIMETON_RETENTION_MAX_RUNTIME_SECONDS": "1.5",
        }
    )

    assert config == RetentionRuntimeConfig(
        enabled=True,
        interval_seconds=900.0,
        batch_size=250,
        max_batches=4,
        max_runtime_seconds=1.5,
    )


def test_factory_builds_disabled_runner_and_initializes_shared_runtime_db(tmp_path: Path):
    path = tmp_path / "runtime.sqlite3"
    runner = build_retention_runner(path, config=RetentionRuntimeConfig())

    assert runner.enabled is False
    assert path.exists()


@pytest.mark.parametrize(
    "config",
    [
        RetentionRuntimeConfig(interval_seconds=10),
        RetentionRuntimeConfig(batch_size=0),
        RetentionRuntimeConfig(max_batches=0),
        RetentionRuntimeConfig(max_runtime_seconds=0),
    ],
)
def test_factory_rejects_unbounded_or_invalid_configuration(tmp_path: Path, config):
    with pytest.raises(ValueError):
        build_retention_runner(tmp_path / "runtime.sqlite3", config=config)
