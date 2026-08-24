#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ARCHITECTURE_SHA = "b47b937873ef980601b5c741af9b327fb18365bc"
SNAPSHOT_ROOT = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "research"
    / "accb_layer_b_snapshot"
    / ARCHITECTURE_SHA
)
MANIFEST_PATH = SNAPSHOT_ROOT / "SNAPSHOT_MANIFEST.json"
PREREG_PATH = SNAPSHOT_ROOT / "ACCB_PREREGISTRATION_v0.4_FROZEN.json"
SCENARIO_PATH = SNAPSHOT_ROOT / "ACCB-DEV-004.scenario.json"

FILLER_CORPUS_VERSION = "accb-layer-b-synthetic-filler-v0.1"
DISTRACTOR_STEMS = (
    "legacyfallback",
    "cachedpolicy",
    "autofallback",
    "stalehandoff",
    "oldrouting",
    "obsoletebudget",
    "deprecateddecision",
)
NEUTRAL_STEMS = (
    "telemetry",
    "checkpoint",
    "inventory",
    "heartbeat",
    "observability",
    "scheduler",
    "archive",
    "baseline",
    "diagnostic",
    "metadata",
    "capacity",
    "latency",
    "checksum",
)

# Retained provider pricing evidence only. A fresh read-only census remains mandatory
# before any paid execution.
RETAINED_PRICING: dict[str, dict[str, Any]] = {
    "z-ai/glm-5.2": {
        "prompt": 0.0002490120633,
        "completion": 0.0007826093418,
        "source_run": 32584584044,
    },
    "deepseek/deepseek-v4-pro-0813": {
        "prompt": 0.00019920965064,
        "completion": 0.00059762895192,
        "source_run": 32595531554,
        "basis": "highest retained time-of-day rate",
    },
    "qwen/qwen3.7-plus": {
        "prompt": 0.0000344951776,
        "completion": 0.0001379807104,
        "source_run": 32584584044,
        "thresholds": [
            {
                "prompt_tokens_gt": 256000,
                "prompt": 0.0001034855328,
                "completion": 0.0004139421312,
            }
        ],
    },
    "moonshotai/kimi-k3": {
        "prompt": 0.0003719011335,
        "completion": 0.0018595056675,
        "source_run": 32595531554,
    },
    "openai/gpt-5.6-sol": {
        "prompt": 0.00021559486,
        "completion": 0.0010779743,
        "source_run": 32619553092,
        "thresholds": [
            {
                "prompt_tokens_gt": 272000,
                "prompt": 0.00043118972,
                "completion": 0.00161696145,
            }
        ],
    },
}

RETAINED_ENDPOINT_CAPABILITIES: dict[str, dict[str, Any]] = {
    "z-ai/glm-5.2": {"transport": "chat", "seed_advertised": True},
    "deepseek/deepseek-v4-pro-0813": {"transport": "chat", "seed_advertised": False},
    "qwen/qwen3.7-plus": {"transport": "chat", "seed_advertised": True},
    "moonshotai/kimi-k3": {"transport": "chat", "seed_advertised": True},
    "openai/gpt-5.6-sol": {"transport": "responses", "seed_advertised": True},
}

# RouterAI documents `seed` as a generic integer parameter, with determinism not
# guaranteed for every model. For the chat adapter this dry-run can verify the
# local wire key without a provider call. The Sol native Responses adapter is
# deliberately left unverified because prior generic controls required native
# translation and we will not guess.
SEED_ADAPTER_CONTRACT = {
    "chat": True,
    "responses": False,
}


class DryRunError(RuntimeError):
    pass


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_snapshot(root: Path = SNAPSHOT_ROOT) -> dict[str, Any]:
    manifest_path = root / "SNAPSHOT_MANIFEST.json"
    manifest = _read_json(manifest_path)
    if manifest.get("source_repository") != "Dimar4713/aimeton-architecture":
        raise DryRunError("unexpected snapshot source repository")
    if manifest.get("source_commit") != ARCHITECTURE_SHA:
        raise DryRunError("unexpected snapshot source commit")

    verified: dict[str, Any] = {}
    for name, meta in (manifest.get("files") or {}).items():
        path = root / name
        if not path.is_file():
            raise DryRunError(f"snapshot file missing: {name}")
        actual = git_blob_sha(path)
        expected = str(meta.get("source_blob_sha") or "")
        if actual != expected:
            raise DryRunError(f"snapshot blob mismatch for {name}: {actual} != {expected}")
        verified[name] = {
            "git_blob_sha": actual,
            "sha256": sha256_file(path),
            "source_path": meta.get("source_path"),
        }
    return {
        "source_repository": manifest["source_repository"],
        "source_commit": manifest["source_commit"],
        "verified_files": verified,
    }


def derive_assembly_seed(
    scenario_id: str, scenario_version: str, anchor_tokens: int
) -> tuple[int, str]:
    digest = hashlib.sha256(
        f"{scenario_id}|{scenario_version}|{anchor_tokens}".encode("utf-8")
    ).hexdigest()
    return int(digest[:8], 16), digest


def _filler_token(seed: int, filler_index: int, density: float) -> tuple[str, bool]:
    # Deterministic stratification: 35% of filler slots are distractors when
    # density=0.35, phase-shifted by the frozen assembly seed.
    modulus = 10000
    cutoff = int(round(density * modulus))
    phase = seed % modulus
    is_distractor = ((filler_index * 7919 + phase) % modulus) < cutoff
    stems = DISTRACTOR_STEMS if is_distractor else NEUTRAL_STEMS
    variant = ((seed ^ (filler_index * 2654435761)) & 0xFFFFFFFF) % len(stems)
    suffix = ((seed + filler_index * 1103515245) & 0xFFFFFFFF) % 997
    return f"{stems[variant]}{suffix:03d}", is_distractor


def assemble_context(
    scenario: dict[str, Any],
    *,
    anchor_tokens: int,
    seed: int,
    density: float,
) -> tuple[str, dict[str, Any]]:
    if anchor_tokens <= 0:
        raise DryRunError("anchor_tokens must be positive")
    positions = list(
        (scenario.get("context_targets") or {}).get("critical_fact_positions") or []
    )
    events = list(scenario.get("events") or [])
    if len(positions) != 5 or len(events) < 6:
        raise DryRunError(
            "Layer B scenario must provide five critical positions and six events"
        )

    # B1..B5 carry temporally changing state; B6 is the final checkpoint/task and
    # is appended after the context so its text is not counted as a critical fact.
    critical_events = events[:5]
    event_token_blocks: list[list[str]] = []
    for event in critical_events:
        payload = str(event.get("payload") or "").split()
        event_token_blocks.append(
            [
                f"[{event['event_id']}:{event['kind']}]",
                *payload,
                f"[/{event['event_id']}]",
            ]
        )

    total_event_tokens = sum(len(block) for block in event_token_blocks)
    if total_event_tokens + 64 >= anchor_tokens:
        raise DryRunError("anchor too small for Layer B event payload")

    tokens: list[str] = []
    event_positions: dict[str, int] = {}
    filler_index = 0
    distractor_count = 0
    filler_count = 0

    for fraction, event, block in zip(positions, critical_events, event_token_blocks):
        desired = int(round(anchor_tokens * float(fraction)))
        desired = max(len(tokens), min(desired, anchor_tokens - total_event_tokens))
        while len(tokens) < desired:
            token, is_distractor = _filler_token(seed, filler_index, density)
            tokens.append(token)
            filler_index += 1
            filler_count += 1
            distractor_count += int(is_distractor)
        event_positions[str(event["event_id"])] = len(tokens)
        tokens.extend(block)
        total_event_tokens -= len(block)

    while len(tokens) < anchor_tokens:
        token, is_distractor = _filler_token(seed, filler_index, density)
        tokens.append(token)
        filler_index += 1
        filler_count += 1
        distractor_count += int(is_distractor)

    if len(tokens) != anchor_tokens:
        raise DryRunError(
            f"logical token target mismatch: {len(tokens)} != {anchor_tokens}"
        )

    context = " ".join(tokens)
    actual_positions = {
        event_id: round(index / anchor_tokens, 6)
        for event_id, index in event_positions.items()
    }
    checkpoint = events[5]
    manifest = {
        "filler_corpus_version": FILLER_CORPUS_VERSION,
        "logical_whitespace_token_target": anchor_tokens,
        "logical_whitespace_tokens": len(tokens),
        "provider_token_count": None,
        "provider_token_count_status": (
            "NOT_MEASURED_OFFLINE_DO_NOT_EQUATE_WITH_BILLED_TOKENS"
        ),
        "context_sha256": hashlib.sha256(context.encode("utf-8")).hexdigest(),
        "context_bytes": len(context.encode("utf-8")),
        "critical_event_logical_positions": actual_positions,
        "target_critical_fact_positions": positions,
        "filler_tokens": filler_count,
        "distractor_filler_tokens": distractor_count,
        "measured_filler_distractor_density": round(
            distractor_count / filler_count if filler_count else 0.0, 6
        ),
        "checkpoint_event_id": checkpoint.get("event_id"),
        "checkpoint_sha256": hashlib.sha256(
            str(checkpoint.get("payload") or "").encode("utf-8")
        ).hexdigest(),
    }
    return context, manifest


def _rates_for(model: str, prompt_tokens: int) -> tuple[float, float]:
    entry = RETAINED_PRICING[model]
    prompt = float(entry["prompt"])
    completion = float(entry["completion"])
    for threshold in entry.get("thresholds") or []:
        if prompt_tokens > int(threshold["prompt_tokens_gt"]):
            prompt = float(threshold["prompt"])
            completion = float(threshold["completion"])
    return prompt, completion


def estimate_cell_cost(
    model: str, prompt_tokens: int, max_output_tokens: int
) -> float:
    prompt_rate, completion_rate = _rates_for(model, prompt_tokens)
    return prompt_tokens * prompt_rate + max_output_tokens * completion_rate


def provider_seed_decision(model: str, assembly_seed: int) -> dict[str, Any]:
    capability = RETAINED_ENDPOINT_CAPABILITIES[model]
    transport = str(capability["transport"])
    advertised = bool(capability["seed_advertised"])
    adapter_verified = bool(SEED_ADAPTER_CONTRACT.get(transport, False))
    if not advertised:
        return {
            "provider_seed": None,
            "send_seed": False,
            "reason": "selected retained endpoint did not advertise seed",
            "transport": transport,
            "seed_advertised": False,
            "adapter_contract_verified_no_paid": adapter_verified,
        }
    if not adapter_verified:
        return {
            "provider_seed": None,
            "send_seed": False,
            "reason": (
                "seed advertised but transport wire contract is not yet no-paid validated"
            ),
            "transport": transport,
            "seed_advertised": True,
            "adapter_contract_verified_no_paid": False,
        }
    return {
        "provider_seed": assembly_seed,
        "send_seed": True,
        "reason": (
            "seed advertised and generic chat wire key is locally contract-validated"
        ),
        "transport": transport,
        "seed_advertised": True,
        "adapter_contract_verified_no_paid": True,
    }


def build_dry_run_report() -> dict[str, Any]:
    snapshot = verify_snapshot()
    prereg = _read_json(PREREG_PATH)
    scenario = _read_json(SCENARIO_PATH)
    if prereg.get("this_document_authorizes_spend_rub") != 0:
        raise DryRunError("frozen prereg unexpectedly authorizes spend")
    if prereg.get("status") != "FROZEN_CALIBRATION_DESIGN_EXECUTION_NOT_AUTHORIZED":
        raise DryRunError("unexpected frozen prereg status")

    tranche = prereg["layer_b_diagnostic_tranche"]
    if tranche["scenario"] != scenario["scenario_id"]:
        raise DryRunError("scenario mismatch between prereg and snapshot")
    if tranche["scenario_version"] != scenario["scenario_version"]:
        raise DryRunError("scenario version mismatch")

    frozen_seed_rows = {
        int(row["anchor_tokens"]): row
        for row in tranche["context_assembly"]["assembly_seeds"]
    }
    contexts: list[dict[str, Any]] = []
    matrix: list[dict[str, Any]] = []
    max_output = int(tranche["generation_policy"]["max_output_tokens"])

    for anchor in map(int, tranche["anchors_tokens"]):
        derived_seed, digest = derive_assembly_seed(
            scenario["scenario_id"], scenario["scenario_version"], anchor
        )
        frozen = frozen_seed_rows[anchor]
        if (
            derived_seed != int(frozen["seed_u32"])
            or digest != frozen["derivation_sha256"]
        ):
            raise DryRunError(f"assembly seed derivation mismatch for {anchor}")
        _, context_manifest = assemble_context(
            scenario,
            anchor_tokens=anchor,
            seed=derived_seed,
            density=float(tranche["distractor_density"]),
        )
        context_manifest.update(
            {
                "anchor_tokens": anchor,
                "assembly_seed_u32": derived_seed,
                "assembly_seed_derivation_sha256": digest,
            }
        )
        contexts.append(context_manifest)

        for model in prereg["model_matrix"]:
            seed_policy = provider_seed_decision(model, derived_seed)
            matrix.append(
                {
                    "model": model,
                    "anchor_tokens": anchor,
                    "max_output_tokens": max_output,
                    "planning_cost_rub": estimate_cell_cost(
                        model, anchor, max_output
                    ),
                    "provider_seed_policy": seed_policy,
                    "provider_pin_required": True,
                    "allow_fallbacks": False,
                }
            )

    total = sum(row["planning_cost_rub"] for row in matrix)
    frozen_total = float(
        prereg["planning_cost_envelope"]["whole_tranche_conservative_estimate_rub"]
    )
    if abs(total - frozen_total) > 0.000001:
        raise DryRunError(f"planning cost mismatch: {total} != {frozen_total}")

    return {
        "schema_version": "0.1",
        "status": "DRY_RUN_NO_MODEL_GENERATION",
        "network_calls_performed": 0,
        "routerai_generation_calls_performed": 0,
        "spend_authorized_rub": 0,
        "architecture_snapshot": snapshot,
        "preregistration_status": prereg["status"],
        "scenario": scenario["scenario_id"],
        "scenario_version": scenario["scenario_version"],
        "filler_corpus_version": FILLER_CORPUS_VERSION,
        "context_manifests": contexts,
        "cells": matrix,
        "planned_calls": len(matrix),
        "planning_cost_recomputed_rub": round(total, 6),
        "planning_cost_frozen_rub": frozen_total,
        "provider_tokenization_boundary": (
            "Offline logical whitespace-token targets are reproducibility scaffolding "
            "only. They are not provider tokenizer counts and must not be used as "
            "billed L_model_input evidence."
        ),
        "remaining_paid_execution_gates": [
            (
                "obtain exact provider/tokenizer input counts or a preregistered "
                "adaptive tokenization method"
            ),
            "perform fresh read-only RouterAI endpoint census",
            "recompute whole-tranche price envelope from fresh selected endpoints",
            "obtain explicit owner-approved spend ceiling",
            "keep paid execution in a separately governed exact-SHA trigger",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="No-paid ACCB Layer B dry-run")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_dry_run_report()
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
