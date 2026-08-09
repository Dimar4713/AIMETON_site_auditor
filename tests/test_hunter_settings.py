from pathlib import Path

import pytest

from app.hunter_settings import HunterSettings, HunterSettingsRepository
from app.models import HuntRequest


def test_hunter_settings_persist_and_apply(tmp_path: Path) -> None:
    path = tmp_path / "runtime.sqlite3"
    repository = HunterSettingsRepository(path)
    saved = repository.save(
        HunterSettings(
            max_queries=32,
            results_per_query=14,
            max_candidates=240,
            minimum_pre_score=25,
            deep_audit_score=55,
            output_limit=60,
            concurrency=6,
        ),
        actor_id=7,
        reason="Расширить покрытие рынка для отладки",
    )

    reloaded = HunterSettingsRepository(path).get()
    assert reloaded == saved
    assert reloaded.updated_by == 7
    assert reloaded.settings.max_queries == 32

    request = HuntRequest(
        region="Красноярск",
        industries=["стоматология"],
        max_queries=1,
        results_per_query=1,
        max_candidates=1,
        output_limit=1,
        concurrency=1,
    )
    effective = repository.apply(request)
    assert effective.max_queries == 32
    assert effective.results_per_query == 14
    assert effective.max_candidates == 240
    assert effective.output_limit == 60
    assert effective.minimum_pre_score == 25
    assert effective.deep_audit_score == 55
    assert effective.concurrency == 6


def test_default_profile_matches_backend_wide_profile(tmp_path: Path) -> None:
    settings = HunterSettingsRepository(tmp_path / "runtime.sqlite3").get().settings
    assert settings.max_queries == 20
    assert settings.results_per_query == 10
    assert settings.max_candidates == 100
    assert settings.output_limit == 25
    assert settings.provider_strategy == "fallback_first_nonempty"


def test_invalid_threshold_relationships_are_rejected(tmp_path: Path) -> None:
    repository = HunterSettingsRepository(tmp_path / "runtime.sqlite3")
    with pytest.raises(ValueError, match="deep_audit_score"):
        repository.save(
            HunterSettings(minimum_pre_score=70, deep_audit_score=50),
            actor_id=1,
            reason="invalid thresholds",
        )

    with pytest.raises(ValueError, match="output_limit"):
        repository.save(
            HunterSettings(max_candidates=10, output_limit=20),
            actor_id=1,
            reason="invalid output size",
        )
