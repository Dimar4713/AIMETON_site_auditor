from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from app.verifier_backend_capability import (
    build_openai_logprob_probe_payload,
    build_openai_structured_score_probe_payload,
    qualify_openai_logprob_response,
)
from app.verifier_model_profiles import resolve_profile


PROBE_COUNT = 2
PREFLIGHT_INPUT_TOKEN_CEILING_PER_CALL = 2048
PREFLIGHT_OUTPUT_TOKEN_CEILING_PER_CALL = 20


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


def _float_env(name: str) -> float:
    raw = _required_env(name)
    try:
        return float(raw)
    except ValueError as exc:
        raise RuntimeError(f"invalid numeric environment variable: {name}") from exc


def _estimated_cost_rub(
    prompt_tokens: int,
    completion_tokens: int,
    *,
    input_rub_per_million: float,
    output_rub_per_million: float,
) -> float:
    return (
        prompt_tokens * input_rub_per_million
        + completion_tokens * output_rub_per_million
    ) / 1_000_000.0


def _usage(body: dict[str, Any]) -> tuple[int | None, int | None, int | None]:
    usage = body.get("usage")
    if not isinstance(usage, dict):
        return None, None, None

    def integer(name: str) -> int | None:
        value = usage.get(name)
        if isinstance(value, bool):
            return None
        if isinstance(value, int) and value >= 0:
            return value
        return None

    return integer("prompt_tokens"), integer("completion_tokens"), integer("total_tokens")


def _safe_provider_metadata(body: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key in ("model", "provider", "system_fingerprint"):
        value = body.get(key)
        if isinstance(value, str) and value:
            safe[key] = value[:200]
    return safe


def _write_result(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _post_json(base_url: str, api_key: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any], int]:
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=60) as response:
        body = json.loads(response.read().decode("utf-8"))
        latency_ms = int((time.monotonic() - started) * 1000)
        if not isinstance(body, dict):
            raise RuntimeError("provider response is not a JSON object")
        return int(response.status), body, latency_ms


def _sanitize_probe(
    body: dict[str, Any],
    *,
    http_status: int,
    latency_ms: int,
    backend_id: str,
    model_id: str,
    input_rub_per_million: float,
    output_rub_per_million: float,
) -> dict[str, Any]:
    report = qualify_openai_logprob_response(
        body,
        backend_id=backend_id,
        model=model_id,
    )
    prompt_tokens, completion_tokens, total_tokens = _usage(body)
    cost = None
    if prompt_tokens is not None and completion_tokens is not None:
        cost = _estimated_cost_rub(
            prompt_tokens,
            completion_tokens,
            input_rub_per_million=input_rub_per_million,
            output_rub_per_million=output_rub_per_million,
        )
    return {
        "qualification_status": report.qualification_status,
        "runtime_logprobs": report.runtime_logprobs,
        "runtime_top_logprobs": report.runtime_top_logprobs,
        "score_token_visible": report.score_token_visible,
        "nondegenerate_distribution": report.nondegenerate_distribution,
        "measured_top_logprobs_width": report.measured_top_logprobs_width,
        "max_score_support": report.evidence.get("max_score_support"),
        "positions_observed": report.evidence.get("positions_observed"),
        "reason_codes": report.reason_codes,
        "http_status": http_status,
        "latency_ms": latency_ms,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
        "actual_estimated_cost_rub": round(cost, 9) if cost is not None else None,
        "provider_metadata": _safe_provider_metadata(body),
    }


def _error_probe(exc: Exception, latency_ms: int) -> dict[str, Any]:
    status = int(exc.code) if isinstance(exc, urllib.error.HTTPError) else None
    reason = f"provider_http_{status}" if status is not None else f"transport_{type(exc).__name__}"
    return {
        "qualification_status": "runtime_incapable",
        "reason_codes": [reason],
        "http_status": status,
        "latency_ms": latency_ms,
        "actual_estimated_cost_rub": None,
    }


def _run_probe(
    base_url: str,
    api_key: str,
    payload: dict[str, Any],
    *,
    backend_id: str,
    model_id: str,
    input_rub_per_million: float,
    output_rub_per_million: float,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        status, body, latency_ms = _post_json(base_url, api_key, payload)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        return _error_probe(exc, int((time.monotonic() - started) * 1000))
    return _sanitize_probe(
        body,
        http_status=status,
        latency_ms=latency_ms,
        backend_id=backend_id,
        model_id=model_id,
        input_rub_per_million=input_rub_per_million,
        output_rub_per_million=output_rub_per_million,
    )


def main() -> int:
    api_key = _required_env("ROUTERAI_API_KEY")
    profile_id = os.getenv("VERIFIER_PROFILE", "").strip() or None
    profile = resolve_profile(profile_id, require_probe_enabled=True)
    if profile.backend_id != "routerai":
        raise RuntimeError(f"unsupported capability-probe backend: {profile.backend_id}")

    max_budget_rub = _float_env("VERIFIER_MAX_BUDGET_RUB")
    result_path = Path(_required_env("VERIFIER_RESULT_PATH"))
    if not (0 < max_budget_rub <= 100.0):
        raise RuntimeError("VERIFIER_MAX_BUDGET_RUB must be in (0, 100]")

    preflight_cost = _estimated_cost_rub(
        PROBE_COUNT * PREFLIGHT_INPUT_TOKEN_CEILING_PER_CALL,
        PROBE_COUNT * PREFLIGHT_OUTPUT_TOKEN_CEILING_PER_CALL,
        input_rub_per_million=profile.input_rub_per_million,
        output_rub_per_million=profile.output_rub_per_million,
    )
    if preflight_cost > max_budget_rub:
        raise RuntimeError(
            f"preflight estimated cost {preflight_cost:.6f} RUB exceeds budget {max_budget_rub:.6f} RUB"
        )

    common = {
        "backend_id": profile.backend_id,
        "model_id": profile.model_id,
        "input_rub_per_million": profile.input_rub_per_million,
        "output_rub_per_million": profile.output_rub_per_million,
    }
    unconstrained = _run_probe(
        profile.base_url,
        api_key,
        build_openai_logprob_probe_payload(profile.model_id, top_logprobs=20),
        **common,
    )
    structured = _run_probe(
        profile.base_url,
        api_key,
        build_openai_structured_score_probe_payload(profile.model_id, top_logprobs=20),
        **common,
    )

    actual_costs = [
        probe.get("actual_estimated_cost_rub")
        for probe in (unconstrained, structured)
        if isinstance(probe.get("actual_estimated_cost_rub"), (int, float))
    ]
    actual_total = float(sum(actual_costs)) if actual_costs else None

    structured_support = int(structured.get("max_score_support") or 0)
    if (
        structured.get("qualification_status") == "runtime_qualified"
        and structured_support >= profile.min_distinct_score_support
    ):
        overall_status = "runtime_qualified"
        reasons: list[str] = []
    elif unconstrained.get("qualification_status") == "runtime_qualified":
        overall_status = "runtime_degraded"
        reasons = ["structured_score_distribution_not_qualified"]
    else:
        overall_status = "runtime_incapable"
        reasons = ["no_qualified_score_distribution_path"]

    pricing = profile.raw["pricing_snapshot"]
    sanitized = {
        "schema_version": "1.2",
        "profile_id": profile.profile_id,
        "profile_lifecycle_status": profile.lifecycle_status,
        "backend_id": profile.backend_id,
        "requested_model": profile.model_id,
        "score_protocol": profile.score_protocol,
        "required_min_distinct_score_support": profile.min_distinct_score_support,
        "qualification_status": overall_status,
        "reason_codes": reasons,
        "probe_modes": {
            "unconstrained_top_logprobs": unconstrained,
            "structured_json_schema": structured,
        },
        "provider_calls": PROBE_COUNT,
        "pricing_snapshot_rub_per_million": {
            "input": profile.input_rub_per_million,
            "output": profile.output_rub_per_million,
        },
        "pricing_snapshot_as_of": pricing.get("as_of"),
        "pricing_source": pricing.get("source"),
        "max_budget_rub": max_budget_rub,
        "preflight_estimated_cost_rub": round(preflight_cost, 9),
        "actual_estimated_cost_rub": round(actual_total, 9) if actual_total is not None else None,
        "raw_response_saved": False,
        "client_release_authority": False,
        "hard_gate_override": False,
    }
    _write_result(result_path, sanitized)

    if actual_total is not None and actual_total > max_budget_rub:
        return 3
    return 0 if overall_status == "runtime_qualified" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"verifier capability probe failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
