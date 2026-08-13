from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import scripts.search_observer_live_second_wave as target
from app.search_observer_scoring import ObservedMarginalYield, assess_second_wave_shadow


_original_scorable_recommendations = target._scorable_recommendations
_original_run_validation = target.run_validation


def _coerce_persisted_recommendation(item: object) -> dict[str, object] | None:
    if isinstance(item, dict):
        return item
    if not isinstance(item, str):
        return None
    try:
        parsed = ast.literal_eval(item)
    except (ValueError, SyntaxError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _compact_controls(metadata: dict[str, object]) -> list[dict[str, object]] | None:
    raw = metadata.get("recommendation_controls_json")
    if raw is None:
        return None
    if not isinstance(raw, str):
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def scorable_recommendations_compat(
    metadata: dict[str, object],
    direction_count: int,
) -> list[dict[str, object]]:
    compact = _compact_controls(metadata)
    if compact is not None:
        return _original_scorable_recommendations(
            {**metadata, "recommendations": compact},
            direction_count,
        )

    raw = metadata.get("recommendations")
    if not isinstance(raw, list):
        return []
    normalized = [
        parsed
        for item in raw
        if (parsed := _coerce_persisted_recommendation(item)) is not None
    ]
    return _original_scorable_recommendations(
        {**metadata, "recommendations": normalized},
        direction_count,
    )


def attach_shadow_decisions(evidence: dict[str, Any]) -> dict[str, Any]:
    """Attach retrospective second-wave decisions to each scored live outcome.

    The decision is evidence-only: it is derived from already-observed marginal
    yield and cannot affect provider selection, execution, or routing.
    """
    for scenario in evidence.get("scenarios", []):
        if not isinstance(scenario, dict):
            continue
        for outcome in scenario.get("outcomes", []):
            if not isinstance(outcome, dict):
                continue
            score = outcome.get("score")
            if not isinstance(score, dict):
                continue
            marginal = score.get("outcome")
            if not isinstance(marginal, dict):
                continue
            observed = ObservedMarginalYield.model_validate(marginal)
            outcome["shadow_second_wave_decision"] = assess_second_wave_shadow(observed).model_dump(mode="json")
    return evidence


async def run_validation_compat(*, budget_rub, output: Path) -> dict[str, object]:
    evidence = await _original_run_validation(budget_rub=budget_rub, output=output)
    attach_shadow_decisions(evidence)
    output.write_text(
        json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return evidence


def main() -> int:
    target._scorable_recommendations = scorable_recommendations_compat
    target.run_validation = run_validation_compat
    return target.main()


if __name__ == "__main__":
    raise SystemExit(main())
