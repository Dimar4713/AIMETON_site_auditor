#!/usr/bin/env python3
"""Validate the generated product projection against canonical infrastructure inventory."""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
PROJECTION_PATH = ROOT / "contracts" / "generated" / "runner-contract-projection.json"
DEFAULT_LABELS = ["self-hosted", "Linux", "X64"]


class ProjectionError(ValueError):
    """Raised when generated runner projection evidence is missing or stale."""


def load_projection(path: Path = PROJECTION_PATH) -> dict[str, Any]:
    try:
        projection = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectionError(f"cannot load generated projection: {exc}") from exc
    if projection.get("schema_version") != "1.0-generated":
        raise ProjectionError("unsupported generated projection schema")
    generation = projection.get("generation")
    if not isinstance(generation, dict) or not generation.get("infrastructure_source_sha"):
        raise ProjectionError("projection generation provenance is incomplete")
    if generation.get("version") != 1 or not str(generation.get("generated_at", "")).endswith("Z"):
        raise ProjectionError("projection generation version or UTC timestamp is invalid")
    if not isinstance(generation.get("sources"), list) or len(generation["sources"]) != 3:
        raise ProjectionError("projection must declare exactly three canonical sources")
    return projection


def get_contract(projection: dict[str, Any], contract_name: str) -> dict[str, Any]:
    contract = projection.get("contracts", {}).get(contract_name)
    if not isinstance(contract, dict):
        raise ProjectionError(f"unknown projected runner contract: {contract_name}")
    return contract


def _canonical_runner(runner: dict[str, Any], source: str) -> dict[str, Any]:
    labels = [*DEFAULT_LABELS, *runner.get("labels", [])]
    return {
        "inventory_key": runner.get("key"),
        "runner_name": runner.get("name"),
        "repository": runner.get("repository"),
        "source": source,
        "labels": labels,
    }


def validate_projection_against_documents(
    projection: dict[str, Any],
    persistent_document: dict[str, Any],
    burst_document: dict[str, Any],
    repository_pools_document: dict[str, Any],
    contract_name: str = "site-auditor-stage",
) -> dict[str, Any]:
    contract = get_contract(projection, contract_name)
    bindings = contract.get("canonical_inventory_keys")
    if not isinstance(bindings, dict):
        raise ProjectionError("canonical inventory bindings are missing")
    persistent_keys = bindings.get("persistent")
    burst_keys = bindings.get("burst")
    if persistent_keys != ["auditor_stage"] or burst_keys != [
        "auditor_burst_stage_01",
        "auditor_burst_stage_02",
    ]:
        raise ProjectionError("unexpected Site Auditor inventory bindings")

    persistent = {runner.get("key"): runner for runner in persistent_document.get("runners", [])}
    burst = {runner.get("key"): runner for runner in burst_document.get("runners", [])}
    expected = []
    for key in persistent_keys:
        if key not in persistent:
            raise ProjectionError(f"canonical persistent runner missing: {key}")
        expected.append(_canonical_runner(persistent[key], "persistent"))
    for key in burst_keys:
        if key not in burst:
            raise ProjectionError(f"canonical burst runner missing: {key}")
        expected.append(_canonical_runner(burst[key], "burst"))

    observed = contract.get("eligible_runners")
    if observed != expected:
        raise ProjectionError("generated runner projection differs from canonical inventory")
    names = [runner["runner_name"] for runner in observed]
    if len(names) != len(set(names)):
        raise ProjectionError("generated runner names must be unique")
    repository = projection.get("repository")
    selector = set(contract.get("selector", []))
    for runner in observed:
        if runner["repository"] != repository:
            raise ProjectionError("generated runner repository ownership mismatch")
        if not selector.issubset(runner["labels"]):
            raise ProjectionError("generated runner does not satisfy contract selector")

    pools = [
        pool
        for pool in repository_pools_document.get("repositories", [])
        if pool.get("repository") == repository
    ]
    if len(pools) != 1:
        raise ProjectionError("canonical Site Auditor repository pool is not unique")
    pool = pools[0]
    expected_burst_names = [
        runner["runner_name"] for runner in observed if runner["source"] == "burst"
    ]
    planned_names = [runner.get("name") for runner in pool.get("planned_runners", [])]
    if planned_names != expected_burst_names:
        raise ProjectionError("canonical repository pool runner names differ from projection")
    if pool.get("baseline_slots") != 1 or pool.get("burst_slots") != 2:
        raise ProjectionError("canonical repository pool slot allocation differs")
    if pool.get("required_labels") != [*contract["selector"], "burst"]:
        raise ProjectionError("canonical repository pool labels differ from projection")
    return contract


def _github_json(url: str, token: str | None) -> dict[str, Any]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "aimeton-runner-projection"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def validate_live_projection(
    projection: dict[str, Any] | None = None,
    contract_name: str = "site-auditor-stage",
) -> dict[str, Any]:
    projection = projection or load_projection()
    generation = projection["generation"]
    repository = generation["infrastructure_repository"]
    token = os.environ.get("GH_TOKEN")
    branch = _github_json(f"https://api.github.com/repos/{repository}/branches/main", token)
    current_main_sha = branch["commit"]["sha"]
    documents: dict[str, dict[str, Any]] = {}
    for source in generation["sources"]:
        path = source["path"]
        encoded_path = "/".join(quote(part, safe="") for part in path.split("/"))
        source_payload = _github_json(
            f"https://api.github.com/repos/{repository}/contents/{encoded_path}"
            f"?ref={generation['infrastructure_source_sha']}",
            token,
        )
        if source_payload.get("sha") != source["git_blob_sha"]:
            raise ProjectionError(f"projection provenance digest mismatch: {path}")
        payload = _github_json(
            f"https://api.github.com/repos/{repository}/contents/{encoded_path}?ref={current_main_sha}",
            token,
        )
        if payload.get("sha") != source["git_blob_sha"]:
            raise ProjectionError(
                f"canonical infrastructure inventory drift: {path}; "
                f"projected={source['git_blob_sha']} current={payload.get('sha')}"
            )
        documents[path] = json.loads(base64.b64decode(payload["content"]).decode("utf-8"))
    contract = validate_projection_against_documents(
        projection,
        documents["ops/main-server/runners.json"],
        documents["ops/burst-runner/site-auditor-runners.json"],
        documents["ops/burst-runner/repository-pools.json"],
        contract_name,
    )
    return {
        "contract": contract_name,
        "canonical_repository": repository,
        "generated_from_sha": generation["infrastructure_source_sha"],
        "validated_current_main_sha": current_main_sha,
        "canonical_drift": False,
        "eligible_runners": contract["eligible_runners"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", default="site-auditor-stage")
    parser.add_argument("--list-source", choices=("persistent", "burst"))
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    projection = load_projection()
    if args.offline:
        contract = get_contract(projection, args.contract)
        result = {"contract": args.contract, "eligible_runners": contract["eligible_runners"]}
    else:
        result = validate_live_projection(projection, args.contract)
    if args.list_source:
        print(json.dumps([
            runner["runner_name"]
            for runner in result["eligible_runners"]
            if runner["source"] == args.list_source
        ], sort_keys=True))
    else:
        print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProjectionError as exc:
        raise SystemExit(f"runner projection validation failed: {exc}")
