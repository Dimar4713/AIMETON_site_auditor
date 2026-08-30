#!/usr/bin/env python3
"""Validate a generated projection and canonical reusable-workflow proof."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROJECTION_PATH = ROOT / "contracts" / "generated" / "runner-contract-projection.json"


class ProjectionError(ValueError):
    """Raised when generated projection or canonical proof is invalid."""


def projection_sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_projection(path: Path = PROJECTION_PATH) -> dict[str, Any]:
    try:
        projection = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectionError(f"cannot load generated projection: {exc}") from exc
    if projection.get("schema_version") != "1.0-generated":
        raise ProjectionError("unsupported generated projection schema")
    generation = projection.get("generation")
    if not isinstance(generation, dict) or generation.get("version") != 2:
        raise ProjectionError("projection generation version is invalid")
    if not str(generation.get("generated_at", "")).endswith("Z"):
        raise ProjectionError("projection generation timestamp must be UTC")
    if not generation.get("infrastructure_source_sha"):
        raise ProjectionError("projection infrastructure source SHA is missing")
    sources = generation.get("sources")
    if not isinstance(sources, list) or len(sources) != 3:
        raise ProjectionError("projection canonical source provenance is incomplete")
    if any(len(str(source.get("git_blob_sha", ""))) != 40 for source in sources):
        raise ProjectionError("projection source digest is invalid")
    payload = projection.get("canonical_payload")
    if not isinstance(payload, dict):
        raise ProjectionError("canonical projection payload is missing")
    expected = generation.get("canonical_projection_sha256")
    if projection_sha256(payload) != expected:
        raise ProjectionError("generated projection payload digest mismatch")
    return projection


def get_contract(projection: dict[str, Any], contract_name: str) -> dict[str, Any]:
    payload = projection["canonical_payload"]
    contract = payload.get("contract")
    if not isinstance(contract, dict) or contract.get("name") != contract_name:
        raise ProjectionError(f"unknown projected runner contract: {contract_name}")
    repository = payload.get("repository")
    names: set[str] = set()
    for runner in contract.get("eligible_runners", []):
        if runner.get("repository") != repository:
            raise ProjectionError("projected runner repository ownership mismatch")
        if runner.get("runner_name") in names:
            raise ProjectionError("projected runner identity is duplicated")
        if not set(contract.get("selector", [])).issubset(runner.get("labels", [])):
            raise ProjectionError("projected runner does not satisfy contract selector")
        names.add(runner["runner_name"])
    return contract


def validate_projection_proof(
    projection: dict[str, Any], canonical_proof_sha256: str | None
) -> dict[str, Any]:
    expected = projection["generation"]["canonical_projection_sha256"]
    if not canonical_proof_sha256:
        raise ProjectionError("canonical infrastructure projection proof is required")
    if canonical_proof_sha256 != expected:
        raise ProjectionError(
            f"canonical infrastructure projection drift: expected={expected} "
            f"observed={canonical_proof_sha256}"
        )
    return projection["canonical_payload"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", default="site-auditor-stage")
    parser.add_argument("--list-source", choices=("persistent", "burst"))
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    projection = load_projection()
    if not args.offline:
        validate_projection_proof(
            projection, os.environ.get("AIMETON_CANONICAL_PROJECTION_SHA256")
        )
    contract = get_contract(projection, args.contract)
    if args.list_source:
        output = [
            runner["runner_name"]
            for runner in contract["eligible_runners"]
            if runner["source"] == args.list_source
        ]
    else:
        output = {
            "contract": args.contract,
            "canonical_projection_sha256": projection["generation"]["canonical_projection_sha256"],
            "canonical_proof_verified": not args.offline,
            "eligible_runners": contract["eligible_runners"],
        }
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProjectionError as exc:
        raise SystemExit(f"runner projection validation failed: {exc}")
