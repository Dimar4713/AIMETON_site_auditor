import json

import pytest

from scripts.search_observer_model_arena_replay import load_cases, resolved_profiles


def test_load_cases_requires_replay_complete_telemetry(tmp_path) -> None:
    payload = {
        "schema_version": 1,
        "mission_id": "dentistry-krasnoyarsk",
        "attempt_id": "wave-1",
        "telemetry": {
            "query_count": 1,
            "result_count": 10,
            "unique_domain_count": 8,
            "duplicate_domain_ratio": 0.2,
            "provider_result_counts": {"searxng": 5, "yandex": 5},
            "attempt_states": {"succeeded": 2},
            "latency_ms_total": 200,
            "degraded_attempts": 0,
            "total_cost_by_currency": {"RUB": "0.01"},
            "directions": [
                {
                    "query": "стоматология Красноярск официальный сайт",
                    "result_count": 10,
                    "unique_domain_count": 8,
                    "duplicate_domain_ratio": 0.2,
                    "provider_result_counts": {"searxng": 5, "yandex": 5},
                    "attempt_states": {"succeeded": 2},
                    "latency_ms_total": 200,
                    "degraded_attempts": 0,
                    "cache_hit": False,
                    "total_cost_by_currency": {"RUB": "0.01"},
                }
            ],
        },
    }
    (tmp_path / "case.json").write_text(json.dumps(payload), encoding="utf-8")
    cases = load_cases(tmp_path)
    assert len(cases) == 1
    assert cases[0].scenario_slug == "dentistry-krasnoyarsk"
    assert cases[0].telemetry.directions[0].query.startswith("стоматология")


def test_load_cases_rejects_empty_directory(tmp_path) -> None:
    with pytest.raises(ValueError, match="no_cases"):
        load_cases(tmp_path)


def test_resolved_profiles_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="unknown_model_profiles"):
        resolved_profiles({"not-a-profile"})
