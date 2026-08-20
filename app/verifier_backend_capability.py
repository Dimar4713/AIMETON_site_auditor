from __future__ import annotations

import math
import re
from typing import Any, Literal

from pydantic import BaseModel, Field


SCORE_TOKENS = tuple("ABCDEFGHIJKLMNOPQRST")


class BackendCapabilityReport(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    backend_id: str = Field(min_length=1)
    model: str = Field(min_length=1)
    endpoint_kind: Literal["openai_chat_completions"] = "openai_chat_completions"
    qualification_status: Literal[
        "contract_candidate",
        "runtime_qualified",
        "runtime_incapable",
        "runtime_degraded",
    ]
    documented_logprobs: bool = False
    documented_top_logprobs: bool = False
    documented_structured_output: bool = False
    runtime_logprobs: bool = False
    runtime_top_logprobs: bool = False
    score_token_visible: bool = False
    nondegenerate_distribution: bool = False
    measured_top_logprobs_width: int = 0
    reason_codes: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    # Capability qualification is only an admission gate for experimentation.
    client_release_authority: Literal[False] = False
    hard_gate_override: Literal[False] = False


def routerai_contract_candidate(model: str = "openai/gpt-4o-mini") -> BackendCapabilityReport:
    """Record documented capabilities without pretending they were measured.

    RouterAI documents OpenAI-compatible `logprobs` and `top_logprobs` request
    fields, plus structured outputs. A live experiment must still prove the
    exact model/provider route returns usable score-token distributions.
    """
    return BackendCapabilityReport(
        backend_id="routerai",
        model=model,
        qualification_status="contract_candidate",
        documented_logprobs=True,
        documented_top_logprobs=True,
        documented_structured_output=True,
        reason_codes=["runtime_probe_required"],
        evidence={
            "api_base": "https://routerai.ru/api/v1",
            "docs": [
                "https://routerai.ru/docs/guides/overview/parameters",
            ],
        },
    )


def build_openai_logprob_probe_payload(model: str, *, top_logprobs: int = 20) -> dict[str, Any]:
    """Build a deliberately tiny unconstrained runtime probe payload."""
    if not 1 <= top_logprobs <= 20:
        raise ValueError("top_logprobs must be in [1, 20]")
    return {
        "model": model,
        "temperature": 0,
        "max_tokens": 4,
        "logprobs": True,
        "top_logprobs": top_logprobs,
        "messages": [
            {
                "role": "system",
                "content": "Return exactly one capital Latin letter from A to T and nothing else.",
            },
            {
                "role": "user",
                "content": "Score this neutral capability probe. Return one letter only.",
            },
        ],
    }


def build_openai_structured_score_probe_payload(
    model: str,
    *,
    top_logprobs: int = 20,
) -> dict[str, Any]:
    """Build a strict JSON-schema score probe constrained to the A-T alphabet.

    The purpose is not to measure task quality. It tests whether a backend can
    expose a non-degenerate score-token distribution when decoding is grammar
    constrained, avoiding generic non-score tokens consuming the top-20 list.
    """
    if not 1 <= top_logprobs <= 20:
        raise ValueError("top_logprobs must be in [1, 20]")
    return {
        "model": model,
        "temperature": 1,
        "max_tokens": 16,
        "logprobs": True,
        "top_logprobs": top_logprobs,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "aimeton_score_probe",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "score": {
                            "type": "string",
                            "enum": list(SCORE_TOKENS),
                        }
                    },
                    "required": ["score"],
                    "additionalProperties": False,
                },
            },
        },
        "messages": [
            {
                "role": "system",
                "content": "Return a score using the required schema. Choose one letter A through T.",
            },
            {
                "role": "user",
                "content": "Neutral score-distribution capability probe.",
            },
        ],
    }


def _iter_logprob_positions(response_body: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        positions = response_body["choices"][0]["logprobs"]["content"]
    except (KeyError, IndexError, TypeError):
        return []
    return positions if isinstance(positions, list) else []


def _score_token_fragment(value: Any) -> str | None:
    """Recover an isolated A-T value from plain or JSON-token fragments."""
    raw = str(value or "")
    match = re.fullmatch(r"[\s\{\}\[\]:,\"']*([A-T])[\s\{\}\[\]:,\"']*", raw)
    return match.group(1) if match else None


def _position_score_support(position: dict[str, Any]) -> set[str]:
    top = position.get("top_logprobs")
    if not isinstance(top, list):
        return set()
    support: set[str] = set()
    for item in top:
        if not isinstance(item, dict):
            continue
        token = _score_token_fragment(item.get("token"))
        if token is not None:
            support.add(token)
    return support


def qualify_openai_logprob_response(
    response_body: dict[str, Any],
    *,
    backend_id: str,
    model: str,
) -> BackendCapabilityReport:
    """Fail closed unless token-level A-T distribution evidence is observable.

    `nondegenerate_distribution` is intentionally based on at least two
    distinct A-T alternatives at one output position. Merely observing two
    different logprob values for arbitrary non-score tokens is insufficient.
    """
    positions = _iter_logprob_positions(response_body)
    if not positions:
        return BackendCapabilityReport(
            backend_id=backend_id,
            model=model,
            qualification_status="runtime_incapable",
            reason_codes=["missing_logprob_content"],
        )

    widths: list[int] = []
    finite_logprobs: list[float] = []
    score_support_sizes: list[int] = []

    for position in positions:
        if not isinstance(position, dict):
            continue
        top = position.get("top_logprobs")
        if not isinstance(top, list):
            continue
        widths.append(len(top))
        score_support_sizes.append(len(_position_score_support(position)))
        for item in top:
            if not isinstance(item, dict):
                continue
            raw_logprob = item.get("logprob")
            if isinstance(raw_logprob, (int, float)) and math.isfinite(float(raw_logprob)):
                finite_logprobs.append(float(raw_logprob))

    measured_width = max(widths, default=0)
    runtime_top_logprobs = measured_width > 0
    max_score_support = max(score_support_sizes, default=0)
    score_token_visible = max_score_support >= 1
    nondegenerate = max_score_support >= 2

    reasons: list[str] = []
    if not runtime_top_logprobs:
        reasons.append("missing_top_logprobs")
    if not score_token_visible:
        reasons.append("score_token_not_visible")
    if score_token_visible and not nondegenerate:
        reasons.append("singleton_score_distribution")
    elif not nondegenerate:
        reasons.append("degenerate_score_distribution")
    if not finite_logprobs:
        reasons.append("missing_finite_logprobs")

    qualified = runtime_top_logprobs and score_token_visible and nondegenerate and bool(finite_logprobs)
    return BackendCapabilityReport(
        backend_id=backend_id,
        model=model,
        qualification_status="runtime_qualified" if qualified else "runtime_degraded",
        runtime_logprobs=True,
        runtime_top_logprobs=runtime_top_logprobs,
        score_token_visible=score_token_visible,
        nondegenerate_distribution=nondegenerate,
        measured_top_logprobs_width=measured_width,
        reason_codes=reasons,
        evidence={
            "positions_observed": len(positions),
            "max_score_support": max_score_support,
        },
    )
