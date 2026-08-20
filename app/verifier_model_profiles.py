from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "config" / "verifier_model_profiles.json"


class VerifierProfileError(RuntimeError):
    pass


@dataclass(frozen=True)
class VerifierModelProfile:
    profile_id: str
    backend_id: str
    base_url: str
    model_id: str
    lifecycle_status: str
    probe_enabled: bool
    calibration_enabled: bool
    score_protocol: str
    input_rub_per_million: float
    output_rub_per_million: float
    min_distinct_score_support: int
    raw: dict[str, Any]


def load_registry(path: Path = DEFAULT_REGISTRY_PATH) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerifierProfileError(f"cannot load verifier profile registry: {exc}") from exc
    if payload.get("schema_version") != "1.0":
        raise VerifierProfileError("unsupported verifier profile registry schema")
    profiles = payload.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise VerifierProfileError("verifier profile registry has no profiles")
    return payload


def default_profile_id(path: Path = DEFAULT_REGISTRY_PATH) -> str:
    payload = load_registry(path)
    profile_id = payload.get("default_profile")
    if not isinstance(profile_id, str) or profile_id not in payload["profiles"]:
        raise VerifierProfileError("invalid default verifier profile")
    return profile_id


def resolve_profile(
    profile_id: str | None = None,
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    require_probe_enabled: bool = False,
    require_calibration_enabled: bool = False,
) -> VerifierModelProfile:
    registry = load_registry(registry_path)
    selected = profile_id or registry.get("default_profile")
    if not isinstance(selected, str) or selected not in registry["profiles"]:
        raise VerifierProfileError(f"unknown verifier profile: {selected!r}")
    raw = registry["profiles"][selected]
    if not isinstance(raw, dict):
        raise VerifierProfileError(f"invalid verifier profile payload: {selected}")

    def nonempty(name: str) -> str:
        value = raw.get(name)
        if not isinstance(value, str) or not value.strip():
            raise VerifierProfileError(f"profile {selected} missing {name}")
        return value.strip()

    pricing = raw.get("pricing_snapshot")
    required = raw.get("required_capabilities")
    if not isinstance(pricing, dict) or not isinstance(required, dict):
        raise VerifierProfileError(f"profile {selected} missing pricing/capability contract")

    try:
        input_price = float(pricing["input_rub_per_million"])
        output_price = float(pricing["output_rub_per_million"])
        min_support = int(required["min_distinct_score_support"])
    except (KeyError, TypeError, ValueError) as exc:
        raise VerifierProfileError(f"profile {selected} has invalid numeric contract") from exc
    if input_price < 0 or output_price < 0:
        raise VerifierProfileError(f"profile {selected} has negative pricing")
    if min_support < 2:
        raise VerifierProfileError(
            f"profile {selected} weakens score-support floor below two"
        )
    for capability in ("logprobs", "top_logprobs", "structured_outputs"):
        if required.get(capability) is not True:
            raise VerifierProfileError(
                f"profile {selected} does not require {capability}"
            )

    probe_enabled = raw.get("probe_enabled") is True
    calibration_enabled = raw.get("calibration_enabled") is True
    if require_probe_enabled and not probe_enabled:
        raise VerifierProfileError(f"profile {selected} is not probe-enabled")
    if require_calibration_enabled and not calibration_enabled:
        blocker = raw.get("calibration_blocker") or "not_admitted"
        raise VerifierProfileError(
            f"profile {selected} is not calibration-enabled: {blocker}"
        )

    return VerifierModelProfile(
        profile_id=selected,
        backend_id=nonempty("backend_id"),
        base_url=nonempty("base_url").rstrip("/"),
        model_id=nonempty("model_id"),
        lifecycle_status=nonempty("lifecycle_status"),
        probe_enabled=probe_enabled,
        calibration_enabled=calibration_enabled,
        score_protocol=nonempty("score_protocol"),
        input_rub_per_million=input_price,
        output_rub_per_million=output_price,
        min_distinct_score_support=min_support,
        raw=raw,
    )
