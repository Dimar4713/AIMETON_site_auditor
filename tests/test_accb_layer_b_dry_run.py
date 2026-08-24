from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import accb_layer_b_dry_run as dry


EXPECTED_CONTEXTS = {
    32768: {
        "seed": 3297921442,
        "sha256": "ea934093e6ba7e27f57edc4e3bd6647232a458b967155f3e1ab26ac13cbe259d",
        "bytes": 470162,
    },
    131072: {
        "seed": 1227261303,
        "sha256": "e3f087711b00dbf1f8d261431cf05899bd5330de511bb1bd2fe5a5bda625ebbd",
        "bytes": 1880717,
    },
    524288: {
        "seed": 990456894,
        "sha256": "b37c2fe5907f80a4e52144c55fe8c3a3bcbbc0e7d81b9f633e41998511b9219e",
        "bytes": 7522522,
    },
}


def test_layer_b_snapshot_is_exact_architecture_blob_copy() -> None:
    evidence = dry.verify_snapshot()
    assert evidence["source_commit"] == dry.ARCHITECTURE_SHA
    files = evidence["verified_files"]
    assert files["ACCB-DEV-004.scenario.json"]["git_blob_sha"] == (
        "7ae1d4cc1819538a3acccc0d7700dc2ca7606161"
    )
    assert files["ACCB_PREREGISTRATION_v0.4_FROZEN.json"]["git_blob_sha"] == (
        "7585474f54bbb4f6e1e3d59085618ab639b1aa4d"
    )


def test_layer_b_seed_derivation_matches_frozen_preregistration() -> None:
    prereg = json.loads(dry.PREREG_PATH.read_text(encoding="utf-8"))
    rows = prereg["layer_b_diagnostic_tranche"]["context_assembly"]["assembly_seeds"]
    for row in rows:
        seed, digest = dry.derive_assembly_seed(
            "ACCB-DEV-004", "0.1", int(row["anchor_tokens"])
        )
        assert seed == row["seed_u32"]
        assert digest == row["derivation_sha256"]


def test_layer_b_smallest_frozen_context_is_deterministic_and_positioned() -> None:
    scenario = json.loads(dry.SCENARIO_PATH.read_text(encoding="utf-8"))
    anchor = 32768
    seed = EXPECTED_CONTEXTS[anchor]["seed"]
    context_a, manifest_a = dry.assemble_context(
        scenario,
        anchor_tokens=anchor,
        seed=seed,
        density=0.35,
    )
    context_b, manifest_b = dry.assemble_context(
        scenario,
        anchor_tokens=anchor,
        seed=seed,
        density=0.35,
    )
    assert context_a == context_b
    assert manifest_a == manifest_b
    assert manifest_a["logical_whitespace_tokens"] == anchor
    assert manifest_a["provider_token_count"] is None
    assert manifest_a["context_sha256"] == EXPECTED_CONTEXTS[anchor]["sha256"]
    assert manifest_a["context_bytes"] == EXPECTED_CONTEXTS[anchor]["bytes"]
    assert abs(manifest_a["measured_filler_distractor_density"] - 0.35) < 0.0001
    actual = list(manifest_a["critical_event_logical_positions"].values())
    target = scenario["context_targets"]["critical_fact_positions"]
    for got, wanted in zip(actual, target):
        assert abs(got - wanted) < 0.0001


def test_layer_b_retained_pricing_math_matches_frozen_planning_estimate() -> None:
    models = list(dry.RETAINED_PRICING)
    anchors = [32768, 131072, 524288]
    total = sum(
        dry.estimate_cell_cost(model, anchor, 8192)
        for anchor in anchors
        for model in models
    )
    assert abs(total - 1001.8273820821095) < 1e-9
    assert round(total, 6) == 1001.827382


def test_layer_b_provider_seed_rule_fails_closed_by_capability_and_transport() -> None:
    seed = 3297921442
    for model in ("z-ai/glm-5.2", "qwen/qwen3.7-plus", "moonshotai/kimi-k3"):
        decision = dry.provider_seed_decision(model, seed)
        assert decision["send_seed"] is True
        assert decision["provider_seed"] == seed
        assert decision["transport"] == "chat"

    deepseek = dry.provider_seed_decision("deepseek/deepseek-v4-pro-0813", seed)
    assert deepseek["send_seed"] is False
    assert deepseek["provider_seed"] is None
    assert deepseek["seed_advertised"] is False

    sol = dry.provider_seed_decision("openai/gpt-5.6-sol", seed)
    assert sol["send_seed"] is False
    assert sol["provider_seed"] is None
    assert sol["transport"] == "responses"
    assert sol["adapter_contract_verified_no_paid"] is False


def test_layer_b_full_dry_run_is_zero_network_zero_spend_and_15_cells() -> None:
    report = dry.build_dry_run_report()
    assert report["status"] == "DRY_RUN_NO_MODEL_GENERATION"
    assert report["network_calls_performed"] == 0
    assert report["routerai_generation_calls_performed"] == 0
    assert report["spend_authorized_rub"] == 0
    assert report["planned_calls"] == 15
    assert report["planning_cost_recomputed_rub"] == 1001.827382
    assert report["planning_cost_frozen_rub"] == 1001.827382

    contexts = {row["anchor_tokens"]: row for row in report["context_manifests"]}
    assert set(contexts) == set(EXPECTED_CONTEXTS)
    for anchor, expected in EXPECTED_CONTEXTS.items():
        assert contexts[anchor]["assembly_seed_u32"] == expected["seed"]
        assert contexts[anchor]["context_sha256"] == expected["sha256"]
        assert contexts[anchor]["context_bytes"] == expected["bytes"]
        assert contexts[anchor]["provider_token_count"] is None

    assert all(row["provider_pin_required"] is True for row in report["cells"])
    assert all(row["allow_fallbacks"] is False for row in report["cells"])
