from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.verifier_model_profiles import (
    VerifierProfileError,
    default_profile_id,
    resolve_profile,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "verifier_model_profiles.json"


def test_default_profile_is_measured_baseline_not_random_candidate():
    assert default_profile_id(REGISTRY) == "routerai-gpt4o-mini"
    profile = resolve_profile(registry_path=REGISTRY, require_probe_enabled=True)
    assert profile.model_id == "openai/gpt-4o-mini"
    assert profile.lifecycle_status == "runtime_baseline"
    assert profile.min_distinct_score_support == 2


def test_qwen_candidate_is_probe_enabled_but_not_calibration_admitted():
    profile = resolve_profile(
        "routerai-qwen35-9b",
        registry_path=REGISTRY,
        require_probe_enabled=True,
    )
    assert profile.model_id == "qwen/qwen3.5-9b"
    assert profile.input_rub_per_million == 11.0
    assert profile.output_rub_per_million == 16.0
    assert profile.lifecycle_status == "candidate"
    assert profile.calibration_enabled is False
    with pytest.raises(VerifierProfileError, match="not calibration-enabled"):
        resolve_profile(
            "routerai-qwen35-9b",
            registry_path=REGISTRY,
            require_calibration_enabled=True,
        )


def test_unknown_model_cannot_bypass_allowlist():
    with pytest.raises(VerifierProfileError, match="unknown verifier profile"):
        resolve_profile("routerai-random-latest", registry_path=REGISTRY)


def test_registry_cannot_weaken_probability_support_floor(tmp_path: Path):
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    payload["profiles"]["routerai-gpt4o-mini"]["required_capabilities"][
        "min_distinct_score_support"
    ] = 1
    weakened = tmp_path / "registry.json"
    weakened.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(VerifierProfileError, match="weakens score-support floor"):
        resolve_profile("routerai-gpt4o-mini", registry_path=weakened)
