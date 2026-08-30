#!/usr/bin/env python3
"""Verify runtime identity against the canonical-infrastructure product projection."""

from __future__ import annotations

import argparse
import json
import os

from validate_runner_contract_projection import (
    ProjectionError,
    get_contract,
    load_projection,
    validate_projection_proof,
)


def verify_runtime_identity(
    contract_name: str,
    actual_name: str,
    *,
    actual_labels: list[str] | None = None,
    require_source: str | None = None,
    canonical_proof_sha256: str | None = None,
) -> dict[str, object]:
    projection = load_projection()
    validate_projection_proof(projection, canonical_proof_sha256)
    contract = get_contract(projection, contract_name)
    eligible = contract["eligible_runners"]
    if require_source is not None:
        eligible = [runner for runner in eligible if runner["source"] == require_source]
    matching = [runner for runner in eligible if runner["runner_name"] == actual_name]
    if len(matching) != 1:
        allowed = [runner["runner_name"] for runner in eligible]
        raise ProjectionError(
            f"runner identity {actual_name!r} is not eligible for {contract_name}; allowed={allowed}"
        )
    runner = matching[0]
    if actual_labels is not None and not set(contract["selector"]).issubset(actual_labels):
        raise ProjectionError(f"runtime labels do not satisfy contract {contract_name}")
    return {
        "contract": contract_name,
        "repository": runner["repository"],
        "runner_name": actual_name,
        "runner_source": runner["source"],
        "identity_membership_verified": True,
        "runtime_labels_verified": actual_labels is not None,
        "selector_authority": (
            "runtime-and-scheduler" if actual_labels is not None else "github-scheduler"
        ),
        "canonical_projection_sha256": canonical_proof_sha256,
        "canonical_proof_verified": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("contract")
    parser.add_argument("--runner-name", default=os.environ.get("RUNNER_NAME", ""))
    parser.add_argument("--runner-labels", default=os.environ.get("AIMETON_RUNNER_LABELS"))
    parser.add_argument("--require-source", choices=("persistent", "burst"))
    args = parser.parse_args()
    labels = args.runner_labels.split(",") if args.runner_labels is not None else None
    if not args.runner_name:
        parser.error("runner identity is empty")
    try:
        result = verify_runtime_identity(
            args.contract,
            args.runner_name,
            actual_labels=labels,
            require_source=args.require_source,
            canonical_proof_sha256=os.environ.get("AIMETON_CANONICAL_PROJECTION_SHA256"),
        )
    except ProjectionError as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
