#!/usr/bin/env python3
"""Compute Search Observer promotion readiness from retained evidence only.

This command performs no provider/search/LLM calls and never changes routing.
It intentionally leaves the quality guard incomplete unless a future owner-approved
quality comparison is supplied through the canonical promotion path. Therefore
retained shadow evidence alone remains fail-closed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.search_observer_promotion import QualityGuard, evaluate_promotion_gate
from app.search_observer_scoring import RecommendationOutcome


def _recommendation_outcomes(payloads: list[dict[str, Any]]) -> list[RecommendationOutcome]:
    results: list[RecommendationOutcome] = []
    for batch_index, payload in enumerate(payloads):
        for scenario_index, scenario in enumerate(payload.get("scenarios", [])):
            scenario_mission = str(
                scenario.get("mission_id")
                or scenario.get("slug")
                or scenario.get("name")
                or f"batch-{batch_index}-scenario-{scenario_index}"
            )
            scenario_attempt = str(
                scenario.get("attempt_id")
                or scenario.get("run_id")
                or f"retained-{batch_index}-{scenario_index}"
            )
            for outcome in scenario.get("outcomes", []):
                score = outcome.get("score") or {}
                if score.get("routing_changed") is True:
                    raise ValueError("promotion_readiness_requires_routing_unchanged")
                if not all(key in score for key in ("action", "confidence", "outcome", "verdict", "score", "reason_code")):
                    continue
                results.append(
                    RecommendationOutcome.model_validate(
                        {
                            "mission_id": score.get("mission_id") or scenario_mission,
                            "attempt_id": score.get("attempt_id") or scenario_attempt,
                            "direction_index": score.get("direction_index", outcome.get("direction_index", 0)),
                            "action": score["action"],
                            "confidence": score["confidence"],
                            "outcome": score["outcome"],
                            "verdict": score["verdict"],
                            "score": score["score"],
                            "reason_code": score["reason_code"],
                            "routing_changed": False,
                        }
                    )
                )
    if not results:
        raise ValueError("promotion_readiness_requires_scored_retained_evidence")
    return results


def build_readiness(
    payloads: list[dict[str, Any]],
    *,
    heterogeneous_batch_count: int,
    recent_batch_supported_ratios: list[float],
) -> dict[str, Any]:
    outcomes = _recommendation_outcomes(payloads)
    decision = evaluate_promotion_gate(
        outcomes,
        heterogeneous_batch_count=heterogeneous_batch_count,
        recent_batch_supported_ratios=recent_batch_supported_ratios,
        quality_guard=QualityGuard(),
    )
    return {
        "evidence_kind": "search_observer_promotion_readiness",
        "decision": decision.model_dump(mode="json"),
        "quality_thresholds_supplied": False,
        "routing_changed": False,
        "steering_enabled": False,
        "promotion_activated": False,
        "reason_code": "offline_readiness_not_steering_activation",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", nargs="+", type=Path)
    parser.add_argument("--heterogeneous-batches", type=int, required=True)
    parser.add_argument("--recent-batch-supported-ratio", action="append", type=float, default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in args.evidence]
    readiness = build_readiness(
        payloads,
        heterogeneous_batch_count=args.heterogeneous_batches,
        recent_batch_supported_ratios=args.recent_batch_supported_ratio,
    )
    text = json.dumps(readiness, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
