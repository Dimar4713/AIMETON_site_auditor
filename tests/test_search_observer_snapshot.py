import json
from decimal import Decimal

from app.search_observer import QueryYieldTelemetry, SearchWaveTelemetry, write_search_wave_snapshot


def _telemetry() -> SearchWaveTelemetry:
    return SearchWaveTelemetry(
        query_count=1,
        result_count=3,
        unique_domain_count=3,
        duplicate_domain_ratio=0.0,
        provider_result_counts={"yandex": 3},
        attempt_states={"succeeded": 1},
        latency_ms_total=120,
        degraded_attempts=0,
        total_cost_by_currency={"RUB": Decimal("0.01")},
        directions=[
            QueryYieldTelemetry(
                query="стоматология Красноярск официальный сайт",
                result_count=3,
                unique_domain_count=3,
                duplicate_domain_ratio=0.0,
                provider_result_counts={"yandex": 3},
                attempt_states={"succeeded": 1},
                latency_ms_total=120,
                degraded_attempts=0,
                cache_hit=False,
                total_cost_by_currency={"RUB": Decimal("0.01")},
            )
        ],
    )


def test_snapshot_writer_preserves_full_direction_telemetry(tmp_path) -> None:
    path = write_search_wave_snapshot(
        _telemetry(),
        directory=str(tmp_path),
        mission_id="dentistry-krasnoyarsk",
        attempt_id="wave-1",
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["mission_id"] == "dentistry-krasnoyarsk"
    assert payload["attempt_id"] == "wave-1"
    assert payload["telemetry"]["query_count"] == 1
    assert payload["telemetry"]["directions"][0]["query"] == "стоматология Красноярск официальный сайт"
    assert payload["telemetry"]["directions"][0]["total_cost_by_currency"] == {"RUB": "0.01"}


def test_snapshot_writer_sanitizes_filename_identity(tmp_path) -> None:
    path = write_search_wave_snapshot(
        _telemetry(),
        directory=str(tmp_path),
        mission_id="case / one",
        attempt_id="wave:1",
    )
    assert path.parent == tmp_path
    assert "/" not in path.name
    assert ":" not in path.name
