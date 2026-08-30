import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


resolver = _load("resolve_runner_contract", ROOT / "scripts" / "resolve_runner_contract.py")
import sys
sys.modules["resolve_runner_contract"] = resolver
verifier = _load("verify_runner_contract_runtime", ROOT / "scripts" / "verify_runner_contract_runtime.py")


def test_resolver_exposes_persistent_and_burst_pool():
    resolved = resolver.resolve_contract("site-auditor-stage")
    assert resolved["runner_name"] == "aimeton-site-auditor-stage"
    assert resolved["eligible_runner_names"] == [
        "aimeton-site-auditor-stage",
        "aimeton-auditor-burst-stage-01",
        "aimeton-auditor-burst-stage-02",
    ]


@pytest.mark.parametrize(
    "runner_name",
    ["aimeton-auditor-burst-stage-01", "aimeton-auditor-burst-stage-02"],
)
def test_burst_acceptance_allows_each_inventory_identity(runner_name):
    result = verifier.verify_runtime_identity(
        "site-auditor-stage", runner_name, require_source="burst"
    )
    assert result == {
        "contract": "site-auditor-stage",
        "runner_name": runner_name,
        "source": "burst",
        "verified": True,
    }


def test_burst_acceptance_rejects_persistent_and_unknown_identity():
    for runner_name in ("aimeton-site-auditor-stage", "unregistered-runner"):
        with pytest.raises(resolver.RunnerContractError):
            verifier.verify_runtime_identity(
                "site-auditor-stage", runner_name, require_source="burst"
            )


def test_inventory_fails_closed_on_duplicate_name(tmp_path):
    inventory = json.loads((ROOT / "ops" / "runner-inventory.json").read_text())
    mutated = copy.deepcopy(inventory)
    mutated["runners"]["auditor_burst_stage_02"]["runner_name"] = (
        mutated["runners"]["auditor_burst_stage_01"]["runner_name"]
    )
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(mutated))
    with pytest.raises(resolver.RunnerContractError, match="unique"):
        resolver.resolve_contract("site-auditor-stage", inventory_path=path)


def test_inventory_fails_closed_on_selector_or_repository_mismatch(tmp_path):
    inventory = json.loads((ROOT / "ops" / "runner-inventory.json").read_text())
    for field, value, pattern in (
        ("labels", ["self-hosted"], "selector"),
        ("repository", "someone/else", "different repository"),
    ):
        mutated = copy.deepcopy(inventory)
        mutated["runners"]["auditor_burst_stage_01"][field] = value
        path = tmp_path / f"inventory-{field}.json"
        path.write_text(json.dumps(mutated))
        with pytest.raises(resolver.RunnerContractError, match=pattern):
            resolver.resolve_contract("site-auditor-stage", inventory_path=path)
