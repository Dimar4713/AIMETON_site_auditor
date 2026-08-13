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
from app.search_observer_promotion import PromotionThresholds
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


def _source_features(snapshot: dict[str, Any] | None) -> dict[str, float | None]:
    if not snapshot:
        return {
            "source_waste_ratio": None,
            "source_raw_per_query": None,
            "source_qualified_per_query": None,
            "source_direct_or_official_per_query": None,
        }
    query_count = int(snapshot.get("query_count") or 0)
    raw = int(snapshot.get("raw_results") or 0)
    duplicates = int(snapshot.get("duplicate_results") or 0)
    excluded = int(snapshot.get("excluded_results") or 0)
    qualified = int(snapshot.get("qualified_candidates") or 0)
    direct = int(snapshot.get("direct_or_official_candidates") or 0)
    wasted = min(raw, duplicates + excluded)
    return {
        "source_waste_ratio": round(wasted / raw, 6) if raw else 0.0,
        "source_raw_per_query": round(raw / query_count, 6) if query_count else 0.0,
        "source_qualified_per_query": round(qualified / query_count, 6) if query_count else 0.0,
        "source_direct_or_official_per_query": round(direct / query_count, 6) if query_count else 0.0,
    }


def _observer_input_features(
    scenario: dict[str, Any], direction_index: int | None
) -> dict[str, Any]:
    retained = scenario.get("observer_input_telemetry")
    if not isinstance(retained, dict):
        return {
            "observer_input_duplicate_domain_ratio": None,
            "observer_input_unique_domain_count": None,
            "observer_input_result_count": None,
            "observer_input_degraded_attempts": None,
            "observer_input_cache_hit": None,
            "observer_input_provider_result_counts": None,
            "observer_input_attempt_states": None,
        }
    if retained.get("routing_changed") is not False:
        raise ValueError("calibration_diagnostics_requires_observer_input_routing_unchanged")
    telemetry = retained.get("telemetry")
    if not isinstance(telemetry, dict) or direction_index is None:
        return {
            "observer_input_duplicate_domain_ratio": None,
            "observer_input_unique_domain_count": None,
            "observer_input_result_count": None,
            "observer_input_degraded_attempts": None,
            "observer_input_cache_hit": None,
            "observer_input_provider_result_counts": None,
            "observer_input_attempt_states": None,
        }
    directions = telemetry.get("directions")
    if not isinstance(directions, list) or direction_index < 0 or direction_index >= len(directions):
        return {
            "observer_input_duplicate_domain_ratio": None,
            "observer_input_unique_domain_count": None,
            "observer_input_result_count": None,
            "observer_input_degraded_attempts": None,
            "observer_input_cache_hit": None,
            "observer_input_provider_result_counts": None,
            "observer_input_attempt_states": None,
        }
    direction = directions[direction_index]
    if not isinstance(direction, dict):
        return {
            "observer_input_duplicate_domain_ratio": None,
            "observer_input_unique_domain_count": None,
            "observer_input_result_count": None,
            "observer_input_degraded_attempts": None,
            "observer_input_cache_hit": None,
            "observer_input_provider_result_counts": None,
            "observer_input_attempt_states": None,
        }
    return {
        "observer_input_duplicate_domain_ratio": direction.get("duplicate_domain_ratio"),
        "observer_input_unique_domain_count": direction.get("unique_domain_count"),
        "observer_input_result_count": direction.get("result_count"),
        "observer_input_degraded_attempts": direction.get("degraded_attempts"),
        "observer_input_cache_hit": direction.get("cache_hit"),
        "observer_input_provider_result_counts": direction.get("provider_result_counts"),
        "observer_input_attempt_states": direction.get("attempt_states"),
    }


def _mean_present(items: list[dict[str, Any]], key: str) -> float | None:
    values = [row[key] for row in items if row.get(key) is not None]
    return round(fmean(values), 6) if values else None


def _confidence_calibration(rows: list[dict[str, Any]]) -> dict[str, Any]:
    comparable = [
        row
        for row in rows
        if row.get("confidence") is not None
        and row.get("deterministic_verdict") in {"supported", "contradicted"}
    ]
    high_floor = PromotionThresholds().high_confidence_floor
    if not comparable:
        return {
            "comparable_count": 0,
            "high_confidence_floor": high_floor,
            "observed_max_confidence": None,
            "high_confidence_count": 0,
            "high_confidence_contradicted_count": 0,
            "high_confidence_contradiction_rate": None,
            "lower_confidence_count": 0,
            "lower_confidence_contradicted_count": 0,
            "lower_confidence_contradiction_rate": None,
            "high_confidence_not_worse": None,
            "definition": "high_uses_canonical_promotion_threshold",
        }

    observed_max = max(float(row["confidence"]) for row in comparable)
    high = [row for row in comparable if float(row["confidence"]) >= high_floor]
    lower = [row for row in comparable if float(row["confidence"]) < high_floor]
    high_contradicted = sum(row["deterministic_verdict"] == "contradicted" for row in high)
    lower_contradicted = sum(row["deterministic_verdict"] == "contradicted" for row in lower)
    high_rate = round(high_contradicted / len(high), 6) if high else None
    lower_rate = round(lower_contradicted / len(lower), 6) if lower else None
    not_worse = None if lower_rate is None or high_rate is None else high_rate <= lower_rate
    return {
        "comparable_count": len(comparable),
        "high_confidence_floor": high_floor,
        "observed_max_confidence": observed_max,
        "high_confidence_count": len(high),
        "high_confidence_contradicted_count": high_contradicted,
        "high_confidence_contradiction_rate": high_rate,
        "lower_confidence_count": len(lower),
        "lower_confidence_contradicted_count": lower_contradicted,
        "lower_confidence_contradiction_rate": lower_rate,
        "high_confidence_not_worse": not_worse,
        "definition": "high_uses_canonical_promotion_threshold",
    }


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
                direction_index = outcome.get("direction_index")
                try:
                    normalized_direction_index = int(direction_index)
                except (TypeError, ValueError):
                    normalized_direction_index = None
                raw_confidence = score.get("confidence")
                try:
                    confidence = float(raw_confidence) if raw_confidence is not None else None
                except (TypeError, ValueError):
                    confidence = None
                rows.append(
                    {
                        "scenario": scenario_id,
                        "direction_index": direction_index,
                        "observer": observer.value,
                        "hindsight": hindsight.value,
                        "cohort": _cohort_name(observer, hindsight),
                        "confidence": confidence,
                        "deterministic_verdict": score.get("verdict"),
                        "quality_gain_observed": decision.quality_gain_observed,
                        "waste_ratio": decision.waste_ratio,
                        "added_qualified_candidates": marginal.added_qualified_candidates,
                        "added_direct_or_official_candidates": marginal.added_direct_or_official_candidates,
                        "added_raw_results": marginal.added_raw_results,
                        **_source_features(outcome.get("source_snapshot")),
                        **_observer_input_features(scenario, normalized_direction_index),
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
            "mean_source_waste_ratio": _mean_present(items, "source_waste_ratio"),
            "mean_source_raw_per_query": _mean_present(items, "source_raw_per_query"),
            "mean_source_qualified_per_query": _mean_present(items, "source_qualified_per_query"),
            "mean_source_direct_or_official_per_query": _mean_present(
                items, "source_direct_or_official_per_query"
            ),
            "source_feature_count": sum(
                row.get("source_waste_ratio") is not None for row in items
            ),
            "mean_observer_input_duplicate_domain_ratio": _mean_present(
                items, "observer_input_duplicate_domain_ratio"
            ),
            "mean_observer_input_unique_domain_count": _mean_present(
                items, "observer_input_unique_domain_count"
            ),
            "mean_observer_input_result_count": _mean_present(
                items, "observer_input_result_count"
            ),
            "mean_observer_input_degraded_attempts": _mean_present(
                items, "observer_input_degraded_attempts"
            ),
            "observer_input_feature_count": sum(
                row.get("observer_input_duplicate_domain_ratio") is not None for row in items
            ),
        }

    disagreements = [row for row in rows if row["cohort"] != "aligned"]
    return {
        "evidence_kind": "search_observer_calibration_diagnostics",
        "sample_count": len(rows),
        "aligned_count": len(rows) - len(disagreements),
        "disagreement_count": len(disagreements),
        "disagreement_ratio": round(len(disagreements) / len(rows), 6),
        "cohorts": cohorts,
        "confidence_calibration": _confidence_calibration(rows),
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
