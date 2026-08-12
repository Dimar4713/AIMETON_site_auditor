from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path

import scripts.search_observer_live_second_wave as target
from scripts.search_observer_live_second_wave_compat import scorable_recommendations_compat
from scripts.search_observer_shadow_benchmark import SCENARIOS, ShadowBenchmarkScenario

OWNER_HARD_CAP_RUB = Decimal("100")
DEFAULT_SCENARIO_SLUGS = (
    "metalworking-ekaterinburg",
    "accounting-novosibirsk",
    "industrial-equipment-kazan",
)
ROTATION_SCENARIO_SLUGS = (
    "construction-moscow",
    "it-services-samara",
    "logistics-rostov-on-don",
    "education-perm",
)
ROTATION_SCENARIOS: tuple[ShadowBenchmarkScenario, ...] = (
    ShadowBenchmarkScenario(
        slug="construction-moscow",
        region="Москва",
        industry="Строительные компании",
    ),
    ShadowBenchmarkScenario(
        slug="it-services-samara",
        region="Самара",
        industry="ИТ-услуги",
    ),
    ShadowBenchmarkScenario(
        slug="logistics-rostov-on-don",
        region="Ростов-на-Дону",
        industry="Логистические компании",
    ),
    ShadowBenchmarkScenario(
        slug="education-perm",
        region="Пермь",
        industry="Образовательные услуги",
    ),
)
THIRD_ROTATION_SCENARIO_SLUGS = (
    "legal-chelyabinsk",
    "auto-service-omsk",
    "medical-labs-ufa",
    "retail-electronics-voronezh",
)
THIRD_ROTATION_SCENARIOS: tuple[ShadowBenchmarkScenario, ...] = (
    ShadowBenchmarkScenario(
        slug="legal-chelyabinsk",
        region="Челябинск",
        industry="Юридические услуги",
    ),
    ShadowBenchmarkScenario(
        slug="auto-service-omsk",
        region="Омск",
        industry="Автосервис",
    ),
    ShadowBenchmarkScenario(
        slug="medical-labs-ufa",
        region="Уфа",
        industry="Медицинские лаборатории",
    ),
    ShadowBenchmarkScenario(
        slug="retail-electronics-voronezh",
        region="Воронеж",
        industry="Розничная электроника",
    ),
)
ALL_BATCH_SCENARIOS = SCENARIOS + ROTATION_SCENARIOS + THIRD_ROTATION_SCENARIOS
MAX_BATCH_SCENARIOS = 4


def parse_budget_rub(raw: str) -> Decimal:
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("heterogeneous_batch_budget_invalid") from exc
    if value <= 0 or value > OWNER_HARD_CAP_RUB:
        raise ValueError("heterogeneous_batch_budget_outside_owner_authorization")
    return value


def select_scenarios(slugs: tuple[str, ...]) -> tuple[ShadowBenchmarkScenario, ...]:
    requested = slugs or DEFAULT_SCENARIO_SLUGS
    if len(requested) < 2 or len(requested) > MAX_BATCH_SCENARIOS:
        raise ValueError("heterogeneous_batch_requires_2_to_4_scenarios")
    if len(set(requested)) != len(requested):
        raise ValueError("heterogeneous_batch_scenarios_must_be_unique")
    by_slug = {item.slug: item for item in ALL_BATCH_SCENARIOS}
    try:
        selected = tuple(by_slug[slug] for slug in requested)
    except KeyError as exc:
        raise ValueError(f"heterogeneous_batch_unknown_scenario:{exc.args[0]}") from exc
    if len({item.region for item in selected}) != len(selected):
        raise ValueError("heterogeneous_batch_regions_must_be_unique")
    if len({item.industry for item in selected}) != len(selected):
        raise ValueError("heterogeneous_batch_industries_must_be_unique")
    return selected


async def run_batch(
    *,
    budget_rub: Decimal,
    scenarios: tuple[ShadowBenchmarkScenario, ...],
    output: Path,
) -> dict[str, object]:
    original_scenarios = target.SCENARIOS
    original_max_scenarios = target.MAX_SCENARIOS
    original_selector = target._scorable_recommendations
    total_actual = Decimal("0")
    collected: list[dict[str, object]] = []

    try:
        target._scorable_recommendations = scorable_recommendations_compat
        target.MAX_SCENARIOS = 1
        for scenario in scenarios:
            remaining = budget_rub - total_actual
            if remaining <= 0:
                raise RuntimeError("heterogeneous_batch_budget_exhausted")
            target.SCENARIOS = (scenario,)
            with tempfile.TemporaryDirectory(prefix="search-observer-batch-") as tmp:
                scenario_output = Path(tmp) / "evidence.json"
                evidence = await target.run_validation(
                    budget_rub=remaining,
                    output=scenario_output,
                )
            actual = Decimal(str(evidence.get("measured_search_cost_rub", "0")))
            total_actual += actual
            if total_actual > budget_rub:
                raise RuntimeError("heterogeneous_batch_measured_budget_exceeded")
            scenario_payload = list(evidence.get("scenarios", []))
            if scenario_payload:
                collected.extend(scenario_payload)
            else:
                collected.append({"slug": scenario.slug, "state": "missing_scenario_evidence"})
    finally:
        target.SCENARIOS = original_scenarios
        target.MAX_SCENARIOS = original_max_scenarios
        target._scorable_recommendations = original_selector

    outcomes = [
        outcome
        for scenario in collected
        for outcome in scenario.get("outcomes", [])
        if isinstance(outcome, dict)
    ]
    result = {
        "schema_version": 1,
        "batch_kind": "heterogeneous_shadow_causal",
        "owner_authorized_budget_rub": str(budget_rub),
        "measured_search_cost_rub": str(total_actual),
        "selected_scenarios": [item.slug for item in scenarios],
        "scenario_attempt_count": len(scenarios),
        "scored_scenario_count": sum(item.get("state") == "scored" for item in collected),
        "outcome_count": len(outcomes),
        "observer_routing_authority": False,
        "premium_escalation": False,
        "routing_changed_any": any(
            item.get("routing_changed") is True
            or any(outcome.get("score", {}).get("routing_changed") is True for outcome in item.get("outcomes", []))
            for item in collected
        ),
        "scenarios": collected,
        "validation_state": "scored" if outcomes else "inconclusive_no_scorable_live_outcome",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget-rub", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--scenario", action="append", default=[])
    parser.add_argument("--rotation", action="store_true")
    parser.add_argument("--third-rotation", action="store_true")
    args = parser.parse_args()
    budget = parse_budget_rub(args.budget_rub)
    requested = tuple(args.scenario)
    if args.rotation and args.third_rotation:
        raise ValueError("heterogeneous_batch_rotation_modes_conflict")
    if args.rotation:
        if requested:
            raise ValueError("heterogeneous_batch_rotation_conflicts_with_explicit_scenarios")
        requested = ROTATION_SCENARIO_SLUGS
    if args.third_rotation:
        if requested:
            raise ValueError("heterogeneous_batch_third_rotation_conflicts_with_explicit_scenarios")
        requested = THIRD_ROTATION_SCENARIO_SLUGS
    scenarios = select_scenarios(requested)
    evidence = asyncio.run(run_batch(budget_rub=budget, scenarios=scenarios, output=Path(args.output)))
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
