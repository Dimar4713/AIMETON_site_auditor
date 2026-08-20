from __future__ import annotations

import math
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
    fields, plus structured outputs.  A live experiment must still prove the
    exact model/provider route returns usable token distributions.
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
    """Build a deliberately tiny runtime probe payload.

    This function performs no network call.  It is safe to construct offline.
    The eventual live probe is bounded to a few output tokens and must be
    executed only through an explicitly admitted provider/budget path.
    """
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


def _iter_logprob_positions(response_body: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        positions = response_body["choices"][0]["logprobs"]["content"]
    except (KeyError, IndexError, TypeError):
        return []
    return positions if isinstance(positions, list) else []


def qualify_openai_logprob_response(
    response_body: dict[str, Any],
    *,
    backend_id: str,
    model: str,
) -> BackendCapabilityReport:
    """Fail closed unless token-level score evidence is actually observable."""
    positions = _iter_logprob_positions(response_body)
    if not positions:
        return BackendCapabilityReport(
            backend_id=backend_id,
            model=model,
            qualification_status="runtime_incapable",
            reason_codes=["missing_logprob_content"],
        )

    widths: list[int] = []
    score_token_visible = False
    finite_logprobs: list[float] = []

    for position in positions:
        if not isinstance(position, dict):
            continue
        top = position.get("top_logprobs")
        if not isinstance(top, list):
            continue
        widths.append(len(top))
        for item in top:
            if not isinstance(item, dict):
                continue
            token = str(item.get("token") or "").strip()
            raw_logprob = item.get("logprob")
            if token in SCORE_TOKENS:
                score_token_visible = True
            if isinstance(raw_logprob, (int, float)) and math.isfinite(float(raw_logprob)):
                finite_logprobs.append(float(raw_logprob))

    measured_width = max(widths, default=0)
    runtime_top_logprobs = measured_width > 0
    nondegenerate = len({round(value, 12) for value in finite_logprobs}) >= 2

    reasons: list[str] = []
    if not runtime_top_logprobs:
        reasons.append("missing_top_logprobs")
    if not score_token_visible:
        reasons.append("score_token_not_visible")
    if not nondegenerate:
        reasons.append("degenerate_logprob_distribution")

    qualified = runtime_top_logprobs and score_token_visible and nondegenerate
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
        evidence={"positions_observed": len(positions)},
    )
