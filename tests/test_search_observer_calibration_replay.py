import hashlib
import json

import scripts.search_observer_calibration_replay as replay


def test_replay_bundle_records_input_provenance(tmp_path, monkeypatch):
    path = tmp_path / "evidence.json"
    payload = {"schema_version": 2, "scenarios": []}
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    path.write_bytes(raw)

    monkeypatch.setattr(
        replay,
        "build_diagnostics",
        lambda payloads: {"sample_count": len(payloads)},
    )

    bundle = replay.build_replay_bundle([path])

    assert bundle["bundle_schema_version"] == 1
    assert bundle["evidence_files"] == [
        {
            "name": "evidence.json",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
            "schema_version": 2,
            "scenario_count": 0,
        }
    ]
    assert bundle["diagnostics"] == {"sample_count": 1}
    assert bundle["routing_changed"] is False
    assert bundle["steering_enabled"] is False
    assert bundle["promotion_eligible"] is False
