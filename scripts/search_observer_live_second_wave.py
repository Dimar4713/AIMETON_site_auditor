from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
from decimal import Decimal, InvalidOperation
from pathlib import Path

import app.discovery as discovery
from app.discovery import EXCLUDED_HOSTS, _domain, _pre_score, run_hunt
from app.hunter_source_role import classify_source_role
from app.models import HuntRequest
from app.search_gateway import SearchRequest, get_search_gateway, search_policy_from_env
from app.search_observer_live_validation import LiveSecondWaveValidationContract
from app.search_observer_multiwave import DirectionWaveOutcomeSnapshot
from app.search_observer_scoring import ObserverRuntimeEvidence
from app.search_observer_trace_link import (
    PersistedRecommendationEvidence,
    score_trace_linked_recommendation,
)
from scripts.search_observer_shadow_benchmark import SCENARIOS

OWNER_HARD_CAP_RUB = Decimal("100")
MAX_INCREMENTAL_QUERIES = 4
WAVE2_RESULT_LIMIT = 11
MAX_SCENARIOS = 2


def parse_budget_rub(raw: str) -> Decimal:
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("live_validation_budget_invalid") from exc
    if value <= 0 or value > OWNER_HARD_CAP_RUB:
        raise ValueError("live_validation_budget_outside_owner_authorization")
    return value


def _excluded_host(host: str) -> bool:
    return not host or host in EXCLUDED_HOSTS or any(host.endswith(f".{item}") for item in EXCLUDED_HOSTS)


def _observe_direction(req: HuntRequest, response) -> dict[str, object]:
    domains: set[str] = set()
    qualified_domains: set[str] = set()
    direct_domains: set[str] = set()
    duplicate_results = 0
    excluded_results = 0

    for item in response.results:
        url = str(item.url)
        host = _domain(url)
        if _excluded_host(host):
            excluded_results += 1
            continue
        if host in domains:
            duplicate_results += 1
            continue
        domains.add(host)
        pre = _pre_score(req, item.title, item.snippet, url)
        if pre.score is None or pre.score < req.minimum_pre_score:
            continue
        qualified_domains.add(host)
        if classify_source_role(item.title, item.snippet, url) == "direct_candidate":
            direct_domains.add(host)

    return {
        "raw_results": len(response.results),
        "domains": domains,
        "qualified_domains": qualified_domains,
        "direct_domains": direct_domains,
        "duplicate_results": duplicate_results,
        "excluded_results": excluded_results,
        "latency_ms": sum(attempt.latency_ms for attempt in response.diagnostics.attempts),
        "cost_rub": Decimal(str(response.diagnostics.total_cost_by_currency.get("RUB", 0))),
    }


def _observer_input_telemetry(telemetry) -> dict[str, object]:
    """Persist the bounded, secret-free input actually seen by the shadow Observer."""
    return {
        "telemetry": telemetry.model_dump(mode="json"),
        "routing_changed": False,
    }


def _source_snapshot(*, mission_id: str, attempt_id: str, direction_index: int, observation: dict[str, object]) -> DirectionWaveOutcomeSnapshot:
    return DirectionWaveOutcomeSnapshot(
        mission_id=mission_id,
        attempt_id=attempt_id,
        wave_index=1,
        direction_index=direction_index,
        query_count=1,
        raw_results=int(observation["raw_results"]),
        unique_domains=len(observation["domains"]),
        qualified_candidates=len(observation["qualified_domains"]),
        direct_or_official_candidates=len(observation["direct_domains"]),
        duplicate_results=int(observation["duplicate_results"]),
        excluded_results=int(observation["excluded_results"]),
        latency_ms=int(observation["latency_ms"]),
        cost_rub=float(observation["cost_rub"]),
        routing_changed=False,
    )


def _later_snapshot(
    *,
    source: DirectionWaveOutcomeSnapshot,
    source_observation: dict[str, object],
    added_observation: dict[str, object],
) -> DirectionWaveOutcomeSnapshot:
    source_domains = set(source_observation["domains"])
    added_domains = set(added_observation["domains"])
    source_qualified = set(source_observation["qualified_domains"])
    added_qualified = set(added_observation["qualified_domains"])
    source_direct = set(source_observation["direct_domains"])
    added_direct = set(added_observation["direct_domains"])
    cross_wave_duplicates = len(source_domains & added_domains)

    return DirectionWaveOutcomeSnapshot(
        mission_id=source.mission_id,
        attempt_id=source.attempt_id,
        wave_index=2,
        direction_index=source.direction_index,
        query_count=source.query_count + 1,
        raw_results=source.raw_results + int(added_observation["raw_results"]),
        unique_domains=len(source_domains | added_domains),
        qualified_candidates=len(source_qualified | added_qualified),
        direct_or_official_candidates=len(source_direct | added_direct),
        duplicate_results=(
            source.duplicate_results
            + int(added_observation["duplicate_results"])
            + cross_wave_duplicates
        ),
        excluded_results=source.excluded_results + int(added_observation["excluded_results"]),
        latency_ms=source.latency_ms + int(added_observation["latency_ms"]),
        cost_rub=round(source.cost_rub + float(added_observation["cost_rub"]), 6),
        routing_changed=False,
    )


def _scorable_recommendations(metadata: dict[str, object], direction_count: int) -> list[dict[str, object]]:
    raw = metadata.get("recommendations")
    if not isinstance(raw, list):
        return []
    selected: list[dict[str, object]] = []
    seen: set[int] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            direction_index = int(item.get("direction_index", -1))
        except (TypeError, ValueError):
            continue
        if direction_index < 0 or direction_index >= direction_count or direction_index in seen:
            continue
        action = str(item.get("action", ""))
        if action == "escalate":
            continue
        seen.add(direction_index)
        selected.append(item)
        if len(selected) >= MAX_INCREMENTAL_QUERIES:
            break
    return selected


def _runtime_from_metadata(metadata: dict[str, object]) -> ObserverRuntimeEvidence:
    return ObserverRuntimeEvidence(
        profile_name=str(metadata["profile_name"]),
        provider=str(metadata["provider"]),
        model=str(metadata["model"]),
        tier=str(metadata["tier"]),
        timeout_seconds=float(metadata["timeout_seconds"]),
        observer_latency_ms=int(metadata["observer_latency_ms"]),
        observer_outcome=str(metadata["observer_outcome"]),
        schema_valid=bool(metadata["schema_valid"]),
        observer_recommendation_count=int(metadata["observer_recommendation_count"]),
        routing_changed=False,
    )


async def run_validation(*, budget_rub: Decimal, output: Path) -> dict[str, object]:
    contract = LiveSecondWaveValidationContract(
        wave_count=2,
        max_incremental_queries=MAX_INCREMENTAL_QUERIES,
        allow_paid_calls=True,
        max_incremental_cost_rub=float(budget_rub),
        owner_spend_authorized=True,
        allow_premium_escalation=False,
        routing_changed=False,
        preserve_provider_policy=True,
        preserve_concurrency_limits=True,
        preserve_cooldown_and_circuits=True,
    )
    assert contract.spend_gate_open is True

    db_path = os.getenv("AIMETON_RUNTIME_DB", "data/runtime-core.sqlite3")
    gateway = get_search_gateway()
    original_builder = discovery.build_search_wave_telemetry
    original_policy_factory = discovery.search_policy_from_env
    total_actual_rub = Decimal("0")
    scenario_evidence: list[dict[str, object]] = []

    try:
        for scenario in SCENARIOS[:MAX_SCENARIOS]:
            remaining = budget_rub - total_actual_rub
            if remaining <= 0:
                raise RuntimeError("live_validation_budget_exhausted_before_wave1")

            base_policy = search_policy_from_env()
            authorized_policy = base_policy.model_copy(
                update={
                    "max_cost_by_currency": {
                        **base_policy.max_cost_by_currency,
                        "RUB": remaining,
                    }
                }
            )
            discovery.search_policy_from_env = lambda: authorized_policy

            captured: dict[str, object] = {}

            def capture_builder(queries, responses):
                telemetry = original_builder(queries, responses)
                captured["queries"] = list(queries)
                captured["responses"] = list(responses)
                captured["telemetry"] = telemetry
                return telemetry

            discovery.build_search_wave_telemetry = capture_builder
            db = sqlite3.connect(db_path, timeout=30)
            try:
                before = db.execute("SELECT COALESCE(MAX(rowid), 0) FROM mission_trace_events").fetchone()[0]
            finally:
                db.close()

            req = HuntRequest(
                region=scenario.region,
                industries=[scenario.industry],
                max_queries=scenario.max_queries,
                results_per_query=scenario.results_per_query,
                max_candidates=scenario.max_candidates,
                output_limit=scenario.output_limit,
                concurrency=2,
            )
            result = await run_hunt(req)
            wave1_rub = Decimal(str(result.search.total_cost_by_currency.get("RUB", 0)))
            total_actual_rub += wave1_rub
            if total_actual_rub > budget_rub:
                raise RuntimeError("live_validation_measured_budget_exceeded_after_wave1")

            db = sqlite3.connect(db_path, timeout=30)
            db.row_factory = sqlite3.Row
            try:
                shadow = db.execute(
                    """
                    SELECT mission_id, attempt_id, metadata_json
                    FROM mission_trace_events
                    WHERE rowid > ?
                      AND component = 'hunter'
                      AND operation = 'hunt_search_wave_shadow_observer'
                    ORDER BY rowid DESC
                    LIMIT 1
                    """,
                    (before,),
                ).fetchone()
            finally:
                db.close()

            if shadow is None or not captured:
                scenario_evidence.append({"slug": scenario.slug, "state": "no_shadow_evidence", "wave1_cost_rub": str(wave1_rub)})
                continue

            metadata = json.loads(shadow["metadata_json"])
            if metadata.get("routing_changed") is not False or metadata.get("observer_outcome") != "succeeded":
                scenario_evidence.append({
                    "slug": scenario.slug,
                    "state": f"observer_{metadata.get('observer_outcome', 'unavailable')}",
                    "wave1_cost_rub": str(wave1_rub),
                })
                continue

            queries = list(captured["queries"])
            responses = list(captured["responses"])
            observer_input = _observer_input_telemetry(captured["telemetry"])
            recommendations = _scorable_recommendations(metadata, len(queries))
            if not recommendations:
                scenario_evidence.append({"slug": scenario.slug, "state": "no_scorable_recommendation", "wave1_cost_rub": str(wave1_rub)})
                continue

            runtime = _runtime_from_metadata(metadata)
            outcomes: list[dict[str, object]] = []
            for item in recommendations:
                direction_index = int(item["direction_index"])
                source_query = queries[direction_index]
                source_response = responses[direction_index]
                source_observation = _observe_direction(req, source_response)
                source = _source_snapshot(
                    mission_id=shadow["mission_id"],
                    attempt_id=shadow["attempt_id"],
                    direction_index=direction_index,
                    observation=source_observation,
                )

                remaining = budget_rub - total_actual_rub
                if remaining <= 0:
                    raise RuntimeError("live_validation_budget_exhausted_before_wave2")
                wave2_policy = authorized_policy.model_copy(
                    update={
                        "max_cost_by_currency": {
                            **authorized_policy.max_cost_by_currency,
                            "RUB": remaining,
                        }
                    }
                )
                response = await gateway.search(
                    SearchRequest(
                        query=source_query,
                        limit=WAVE2_RESULT_LIMIT,
                        mission_id=shadow["mission_id"],
                        correlation_id=shadow["attempt_id"],
                    ),
                    wave2_policy,
                )
                added_observation = _observe_direction(req, response)
                added_rub = Decimal(str(added_observation["cost_rub"]))
                total_actual_rub += added_rub
                if total_actual_rub > budget_rub:
                    raise RuntimeError("live_validation_measured_budget_exceeded_after_wave2")

                later = _later_snapshot(
                    source=source,
                    source_observation=source_observation,
                    added_observation=added_observation,
                )
                recommendation = PersistedRecommendationEvidence(
                    mission_id=shadow["mission_id"],
                    attempt_id=shadow["attempt_id"],
                    source_wave_index=1,
                    direction_index=direction_index,
                    action=str(item["action"]),
                    confidence=float(item["confidence"]),
                    runtime=runtime,
                    routing_changed=False,
                )
                scored = score_trace_linked_recommendation(
                    recommendation=recommendation,
                    source_wave=source,
                    later_wave=later,
                )
                outcomes.append({
                    "direction_index": direction_index,
                    "source_query": source_query,
                    "wave1_limit": scenario.results_per_query,
                    "wave2_limit": WAVE2_RESULT_LIMIT,
                    "recommendation": {
                        "action": str(item["action"]),
                        "confidence": float(item["confidence"]),
                        "rationale": str(item.get("rationale", ""))[:300],
                    },
                    "source_snapshot": source.model_dump(mode="json"),
                    "later_snapshot": later.model_dump(mode="json"),
                    "score": scored.model_dump(mode="json"),
                    "wave2_cost_rub": str(added_rub),
                })

            scenario_evidence.append({
                "slug": scenario.slug,
                "state": "scored",
                "mission_id": shadow["mission_id"],
                "attempt_id": shadow["attempt_id"],
                "wave1_cost_rub": str(wave1_rub),
                "observer_model": metadata.get("model"),
                "observer_tier": metadata.get("tier"),
                "observer_latency_ms": metadata.get("observer_latency_ms"),
                "observer_input_telemetry": observer_input,
                "routing_changed": False,
                "outcomes": outcomes,
            })
            if outcomes:
                break
    finally:
        discovery.build_search_wave_telemetry = original_builder
        discovery.search_policy_from_env = original_policy_factory

    evidence = {
        "schema_version": 2,
        "owner_authorized_budget_rub": str(budget_rub),
        "measured_search_cost_rub": str(total_actual_rub),
        "max_scenarios": MAX_SCENARIOS,
        "max_incremental_queries": MAX_INCREMENTAL_QUERIES,
        "wave2_result_limit": WAVE2_RESULT_LIMIT,
        "observer_routing_authority": False,
        "premium_escalation": False,
        "routing_changed_any": False,
        "scenarios": scenario_evidence,
    }
    if total_actual_rub > budget_rub:
        raise RuntimeError("live_validation_final_budget_assertion_failed")
    if not any(item.get("state") == "scored" and item.get("outcomes") for item in scenario_evidence):
        evidence["validation_state"] = "inconclusive_no_scorable_live_outcome"
    else:
        evidence["validation_state"] = "scored"

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget-rub", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    budget = parse_budget_rub(args.budget_rub)
    evidence = asyncio.run(run_validation(budget_rub=budget, output=Path(args.output)))
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
