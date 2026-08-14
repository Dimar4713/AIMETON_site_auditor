#!/usr/bin/env python3
"""Compute Search Observer promotion readiness from retained evidence only.

This command performs no provider/search/LLM calls and never changes routing.
When an existing runtime DB is supplied, it reads the persisted admin quality
policy in SQLite read-only mode and applies it to retained source/later quality
evidence. Missing policy, missing evidence, or unknown resource-cap compliance
keeps the promotion gate fail-closed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.search_observer_promotion import QualityGuard, evaluate_promotion_gate
from app.search_observer_quality_evidence import load_shadow_quality_proxy
from app.search_observer_quality_policy import (
    QualityFirstPromotionPolicy,
    derive_quality_first_guard,
)
from app.search_observer_scoring import RecommendationOutcome
from app.search_quality_policy_settings import load_search_quality_policy_readonly


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


def _combined_quality_payload(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "scenarios": [
            scenario
            for payload in payloads
            for scenario in payload.get("scenarios", [])
        ]
    }


def _quality_guard_from_retained_evidence(
    payloads: list[dict[str, Any]],
    *,
    quality_policy: QualityFirstPromotionPolicy | None,
    resource_policy_compliant: bool | None,
) -> tuple[QualityGuard, bool]:
    if quality_policy is None:
        return QualityGuard(), False
    try:
        proxy = load_shadow_quality_proxy(_combined_quality_payload(payloads))
    except ValueError:
        return QualityGuard(), False
    guard = derive_quality_first_guard(
        baseline=proxy.source,
        candidate=proxy.later,
        resource_policy_compliant=resource_policy_compliant,
        policy=quality_policy,
    )
    return guard, True


def build_readiness(
    payloads: list[dict[str, Any]],
    *,
    heterogeneous_batch_count: int,
    recent_batch_supported_ratios: list[float],
    quality_policy: QualityFirstPromotionPolicy | None = None,
    quality_policy_persisted: bool = False,
    resource_policy_compliant: bool | None = None,
) -> dict[str, Any]:
    outcomes = _recommendation_outcomes(payloads)
    quality_guard, quality_evidence_loaded = _quality_guard_from_retained_evidence(
        payloads,
        quality_policy=quality_policy,
        resource_policy_compliant=resource_policy_compliant,
    )
    decision = evaluate_promotion_gate(
        outcomes,
        heterogeneous_batch_count=heterogeneous_batch_count,
        recent_batch_supported_ratios=recent_batch_supported_ratios,
        quality_guard=quality_guard,
    )
    return {
        "evidence_kind": "search_observer_promotion_readiness",
        "decision": decision.model_dump(mode="json"),
        "quality_thresholds_supplied": quality_policy is not None,
        "quality_policy_persisted": bool(quality_policy is not None and quality_policy_persisted),
        "quality_evidence_loaded": quality_evidence_loaded,
        "resource_policy_compliant": resource_policy_compliant,
        "routing_changed": False,
        "steering_enabled": False,
        "promotion_activated": False,
        "reason_code": "offline_readiness_not_steering_activation",
    }


def _parse_optional_bool(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    if normalized == "unknown":
        return None
    raise ValueError("resource_policy_compliant_must_be_true_false_or_unknown")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", nargs="+", type=Path)
    parser.add_argument("--heterogeneous-batches", type=int, required=True)
    parser.add_argument("--recent-batch-supported-ratio", action="append", type=float, default=[])
    parser.add_argument(
        "--runtime-db",
        type=Path,
        help="Existing runtime SQLite DB; read-only admin quality policy source.",
    )
    parser.add_argument(
        "--resource-policy-compliant",
        choices=("true", "false", "unknown"),
        default="unknown",
        help="Whether the measured candidate stayed inside existing hard caps.",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in args.evidence]
    quality_policy = None
    quality_policy_persisted = False
    if args.runtime_db is not None:
        loaded = load_search_quality_policy_readonly(args.runtime_db)
        if loaded.persisted:
            quality_policy = loaded.record.policy
            quality_policy_persisted = True

    readiness = build_readiness(
        payloads,
        heterogeneous_batch_count=args.heterogeneous_batches,
        recent_batch_supported_ratios=args.recent_batch_supported_ratio,
        quality_policy=quality_policy,
        quality_policy_persisted=quality_policy_persisted,
        resource_policy_compliant=_parse_optional_bool(args.resource_policy_compliant),
    )
    text = json.dumps(readiness, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
