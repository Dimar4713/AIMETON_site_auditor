#!/usr/bin/env python3
"""Offline diagnostics for Search Observer advice versus stored hindsight.

This command reads retained evidence JSON only. It performs no provider/LLM calls,
does not mutate routing, and does not define promotion thresholds.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import fmean
from typing import Any

from app.search_observer_llm import ObserverAction
from app.search_observer_scoring import (
    ObservedMarginalYield,
    SecondWaveShadowAction,
    assess_second_wave_shadow,
)


def _observer_treatment(action: ObserverAction) -> SecondWaveShadowAction | None:
    if action in {ObserverAction.CONTINUE, ObserverAction.BOOST}:
        return SecondWaveShadowAction.CONTINUE
    if action in {ObserverAction.REFINE, ObserverAction.SLOW}:
        return SecondWaveShadowAction.REFINE
    if action == ObserverAction.STOP:
        return SecondWaveShadowAction.SKIP
    return None


def _cohort_name(
    observer: SecondWaveShadowAction,
    hindsight: SecondWaveShadowAction,
) -> str:
    if observer == hindsight:
        return "aligned"
    if observer == SecondWaveShadowAction.REFINE and hindsight == SecondWaveShadowAction.CONTINUE:
        return "over_refine"
    if observer == SecondWaveShadowAction.CONTINUE and hindsight == SecondWaveShadowAction.REFINE:
        return "under_refine"
    if observer == SecondWaveShadowAction.CONTINUE and hindsight == SecondWaveShadowAction.SKIP:
        return "continue_without_gain"
    return "other_disagreement"


def build_diagnostics(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for batch_index, payload in enumerate(payloads):
        for scenario in payload.get("scenarios", []):
            scenario_id = (
                scenario.get("slug")
                or scenario.get("name")
                or scenario.get("mission_id")
                or f"batch-{batch_index}"
            )
            for outcome in scenario.get("outcomes", []):
                score = outcome.get("score") or {}
                if score.get("routing_changed") is True:
                    raise ValueError("calibration_diagnostics_requires_routing_unchanged")
                raw_marginal = score.get("outcome")
                raw_action = score.get("action")
                if raw_marginal is None or raw_action is None:
                    continue
                observer = _observer_treatment(ObserverAction(raw_action))
                if observer is None:
                    continue
                marginal = ObservedMarginalYield.model_validate(raw_marginal)
                decision = assess_second_wave_shadow(marginal)
                hindsight = decision.preferred_action
                rows.append(
                    {
                        "scenario": scenario_id,
                        "direction_index": outcome.get("direction_index"),
                        "observer": observer.value,
                        "hindsight": hindsight.value,
                        "cohort": _cohort_name(observer, hindsight),
                        "quality_gain_observed": decision.quality_gain_observed,
                        "waste_ratio": decision.waste_ratio,
                        "added_qualified_candidates": marginal.added_qualified_candidates,
                        "added_direct_or_official_candidates": marginal.added_direct_or_official_candidates,
                        "added_raw_results": marginal.added_raw_results,
                    }
                )

    if not rows:
        raise ValueError("calibration_diagnostics_requires_comparable_evidence")

    cohorts: dict[str, dict[str, Any]] = {}
    for name in (
        "aligned",
        "over_refine",
        "under_refine",
        "continue_without_gain",
        "other_disagreement",
    ):
        items = [row for row in rows if row["cohort"] == name]
        cohorts[name] = {
            "count": len(items),
            "mean_waste_ratio": round(fmean(row["waste_ratio"] for row in items), 6) if items else None,
            "mean_added_qualified_candidates": round(
                fmean(row["added_qualified_candidates"] for row in items), 6
            ) if items else None,
            "mean_added_direct_or_official_candidates": round(
                fmean(row["added_direct_or_official_candidates"] for row in items), 6
            ) if items else None,
        }

    disagreements = [row for row in rows if row["cohort"] != "aligned"]
    return {
        "evidence_kind": "search_observer_calibration_diagnostics",
        "sample_count": len(rows),
        "aligned_count": len(rows) - len(disagreements),
        "disagreement_count": len(disagreements),
        "disagreement_ratio": round(len(disagreements) / len(rows), 6),
        "cohorts": cohorts,
        "disagreements": disagreements,
        "routing_changed": False,
        "steering_enabled": False,
        "promotion_eligible": False,
        "reason_code": "offline_diagnostic_not_promotion_gate",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in args.evidence]
    diagnostics = build_diagnostics(payloads)
    text = json.dumps(diagnostics, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
