#!/usr/bin/env python3
"""Resolve a Site Auditor runner contract to its eligible physical identities."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_PATH = ROOT / "contracts" / "runner-contracts.json"
INVENTORY_PATH = ROOT / "ops" / "runner-inventory.json"


class RunnerContractError(ValueError):
    """Raised when a runner contract or inventory is unsafe to resolve."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RunnerContractError(f"cannot load {path.relative_to(ROOT)}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RunnerContractError(f"{path.relative_to(ROOT)} must contain a JSON object")
    return payload


def resolve_contract(
    contract_name: str,
    *,
    contracts_path: Path = CONTRACTS_PATH,
    inventory_path: Path = INVENTORY_PATH,
) -> dict[str, Any]:
    contracts_document = _load_json(contracts_path)
    inventory_document = _load_json(inventory_path)
    contracts = contracts_document.get("contracts")
    runners = inventory_document.get("runners")
    if not isinstance(contracts, dict) or not isinstance(runners, dict):
        raise RunnerContractError("contracts and inventory runners must be JSON objects")
    contract = contracts.get(contract_name)
    if not isinstance(contract, dict):
        raise RunnerContractError(f"unknown runner contract: {contract_name}")

    repository = contracts_document.get("repository")
    if repository != inventory_document.get("repository"):
        raise RunnerContractError("contract and inventory repository ownership differ")

    selector = contract.get("selector")
    baseline_key = contract.get("inventory_key")
    burst_keys = contract.get("burst_inventory_keys", [])
    if not isinstance(selector, list) or not selector or not all(isinstance(v, str) and v for v in selector):
        raise RunnerContractError(f"contract {contract_name} has an invalid selector")
    if not isinstance(baseline_key, str) or not baseline_key:
        raise RunnerContractError(f"contract {contract_name} has an invalid inventory_key")
    if not isinstance(burst_keys, list) or not all(isinstance(v, str) and v for v in burst_keys):
        raise RunnerContractError(f"contract {contract_name} has invalid burst_inventory_keys")
    inventory_keys = [baseline_key, *burst_keys]
    if len(inventory_keys) != len(set(inventory_keys)):
        raise RunnerContractError(f"contract {contract_name} contains duplicate inventory keys")

    eligible: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    required_labels = set(selector)
    for inventory_key in inventory_keys:
        runner = runners.get(inventory_key)
        if not isinstance(runner, dict):
            raise RunnerContractError(f"contract {contract_name} references unknown inventory key {inventory_key}")
        name = runner.get("runner_name")
        labels = runner.get("labels")
        source = runner.get("source")
        if not isinstance(name, str) or not name or name in seen_names:
            raise RunnerContractError(f"inventory runner names must be non-empty and unique: {inventory_key}")
        if runner.get("repository") != repository:
            raise RunnerContractError(f"runner {inventory_key} belongs to a different repository")
        if not isinstance(labels, list) or not all(isinstance(v, str) and v for v in labels):
            raise RunnerContractError(f"runner {inventory_key} has invalid labels")
        if not required_labels.issubset(labels):
            raise RunnerContractError(f"runner {inventory_key} does not satisfy contract selector")
        if source not in {"persistent", "burst"}:
            raise RunnerContractError(f"runner {inventory_key} has invalid source")
        seen_names.add(name)
        eligible.append(
            {
                "inventory_key": inventory_key,
                "runner_name": name,
                "source": source,
                "labels": labels,
            }
        )

    return {
        "contract": contract_name,
        "capability": contract.get("capability"),
        "repository": repository,
        "selector": selector,
        "runner_name": eligible[0]["runner_name"],
        "labels": eligible[0]["labels"],
        "eligible_runner_names": [runner["runner_name"] for runner in eligible],
        "eligible_runners": eligible,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("contract")
    args = parser.parse_args()
    try:
        print(json.dumps(resolve_contract(args.contract), sort_keys=True))
    except RunnerContractError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
