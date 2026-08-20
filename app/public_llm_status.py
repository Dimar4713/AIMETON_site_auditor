from __future__ import annotations

from typing import Any


_PUBLIC_INPUT_LIMITS: dict[str, int] = {
    "official_text_chars": 10_000_000,
    "external_context_chars": 10_000_000,
    "external_source_count": 10_000,
    "schema_chars": 10_000_000,
    "estimated_total_input_chars": 30_000_000,
}
_PUBLIC_OUTCOMES = frozenset({"succeeded", "timeout", "failed"})


def _bounded_non_negative_int(value: Any, maximum: int) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed < 0:
        return None
    return min(parsed, maximum)


def project_public_llm_input_metrics(metadata: dict[str, Any] | None) -> dict[str, int] | None:
    """Project only bounded aggregate LLM input metrics for public status.

    Prompt text, query text, URLs, raw responses, provider payloads and arbitrary
    metadata keys are intentionally impossible to pass through this allow-list.
    """
    if not metadata:
        return None
    projected: dict[str, int] = {}
    for key, maximum in _PUBLIC_INPUT_LIMITS.items():
        value = _bounded_non_negative_int(metadata.get(key), maximum)
        if value is not None:
            projected[key] = value
    return projected or None


def project_public_llm_outcome(metadata: dict[str, Any] | None) -> str | None:
    if not metadata:
        return None
    value = metadata.get("outcome")
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized if normalized in _PUBLIC_OUTCOMES else None
