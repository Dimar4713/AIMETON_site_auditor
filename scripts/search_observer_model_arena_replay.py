from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.search_observer import SearchWaveTelemetry
from app.search_observer_llm import evaluate_search_wave_shadow_with_model
from app.search_observer_model_arena import (
    ModelArenaCase,
    ModelArenaObservation,
    evaluate_model_arena_case,
    summarize_model_arena,
)
from app.search_observer_models import OBSERVER_MODEL_PROFILES


def load_cases(directory: Path) -> list[ModelArenaCase]:
    cases: list[ModelArenaCase] = []
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        telemetry = SearchWaveTelemetry.model_validate(payload["telemetry"])
        cases.append(
            ModelArenaCase(
                scenario_slug=str(payload.get("mission_id") or path.stem),
                telemetry=telemetry,
            )
        )
    if not cases:
        raise ValueError("model_arena_replay_has_no_cases")
    return cases


def resolved_profiles(selected: set[str] | None = None):
    profiles = []
    for profile in OBSERVER_MODEL_PROFILES:
        if selected and profile.name not in selected:
            continue
        profiles.append(profile.resolve())
    if selected:
        known = {item.profile_name for item in profiles}
        missing = selected - known
        if missing:
            raise ValueError(f"unknown_model_profiles:{','.join(sorted(missing))}")
    return profiles


async def run_arena(cases: list[ModelArenaCase], profiles) -> list[ModelArenaObservation]:
    observations: list[ModelArenaObservation] = []
    for model in profiles:
        for case in cases:
            observations.append(
                await evaluate_model_arena_case(
                    case=case,
                    model=model,
                    evaluator=evaluate_search_wave_shadow_with_model,
                )
            )
    return observations


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--profiles", default="")
    parser.add_argument("--max-model-calls", type=int, default=24)
    args = parser.parse_args()

    directory = Path(args.input_dir)
    selected = {item.strip() for item in args.profiles.split(",") if item.strip()} or None
    cases = load_cases(directory)
    profiles = resolved_profiles(selected)
    configured_count = sum(1 for profile in profiles if profile.configured)
    planned_calls = configured_count * len(cases)
    if planned_calls > args.max_model_calls:
        raise ValueError(f"model_arena_call_cap_exceeded:{planned_calls}>{args.max_model_calls}")

    observations = asyncio.run(run_arena(cases, profiles))
    summaries = summarize_model_arena(observations)
    payload = {
        "replay_only": True,
        "search_calls": 0,
        "case_count": len(cases),
        "profile_count": len(profiles),
        "configured_profile_count": configured_count,
        "planned_model_calls": planned_calls,
        "routing_changed_any": any(item.routing_changed for item in observations),
        "profiles": [profile.safe_descriptor() for profile in profiles],
        "observations": [item.model_dump(mode="json") for item in observations],
        "summary": [item.model_dump(mode="json") for item in summaries],
    }
    if payload["routing_changed_any"]:
        raise ValueError("model_arena_routing_invariant_violated")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
