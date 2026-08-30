#!/usr/bin/env python3
"""Fail closed unless the current runner is eligible for a Site Auditor contract."""

from __future__ import annotations

import argparse
import json
import os

from resolve_runner_contract import RunnerContractError, resolve_contract


def verify_runtime_identity(
    contract_name: str,
    actual_name: str,
    *,
    actual_labels: list[str] | None = None,
    require_source: str | None = None,
) -> dict[str, object]:
    resolved = resolve_contract(contract_name)
    eligible = resolved["eligible_runners"]
    if require_source is not None:
        eligible = [runner for runner in eligible if runner["source"] == require_source]
    matching = [runner for runner in eligible if runner["runner_name"] == actual_name]
    if len(matching) != 1:
        allowed = [runner["runner_name"] for runner in eligible]
        raise RunnerContractError(
            f"runner identity {actual_name!r} is not eligible for {contract_name}; allowed={allowed}"
        )
    runner = matching[0]
    if actual_labels is not None and not set(resolved["selector"]).issubset(actual_labels):
        raise RunnerContractError(f"runtime labels do not satisfy contract {contract_name}")
    return {
        "contract": contract_name,
        "runner_name": actual_name,
        "source": runner["source"],
        "verified": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("contract")
    parser.add_argument("--runner-name", default=os.environ.get("RUNNER_NAME", ""))
    parser.add_argument("--runner-labels", default=os.environ.get("AIMETON_RUNNER_LABELS"))
    parser.add_argument("--require-source", choices=("persistent", "burst"))
    args = parser.parse_args()
    labels = args.runner_labels.split(",") if args.runner_labels else None
    if not args.runner_name:
        parser.error("runner identity is empty")
    try:
        result = verify_runtime_identity(
            args.contract,
            args.runner_name,
            actual_labels=labels,
            require_source=args.require_source,
        )
    except RunnerContractError as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
