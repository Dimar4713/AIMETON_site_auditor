#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import urllib.request


def compact(payload: dict) -> dict:
    rows = []
    for row in payload.get("rows") or []:
        score = row.get("score") or {}
        endpoint = row.get("endpoint") or {}
        usage = row.get("usage") or {}
        cost_latency = ((row.get("manifest") or {}).get("cost_latency") or {})
        rows.append({
            "model": row.get("model_identifier"),
            "status": row.get("status"),
            "endpoint_tag": endpoint.get("tag"),
            "provider_name": endpoint.get("provider_name"),
            "context_length": endpoint.get("context_length"),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "elapsed_seconds": cost_latency.get("wall_clock_seconds"),
            "estimated_cost_rub": row.get("estimated_cost_rub"),
            "ACI": score.get("ACI"),
            "ACI_min": score.get("ACI_min"),
            "critical_failure_count": score.get("critical_failure_count"),
            "critical_failures": score.get("critical_failures"),
            "error": row.get("error"),
        })
    return {
        "experiment_id": payload.get("experiment_id"),
        "architecture_sha": payload.get("architecture_sha"),
        "site_auditor_sha": payload.get("site_auditor_sha"),
        "budget_ceiling_rub": payload.get("budget_ceiling_rub"),
        "estimated_spend_rub": payload.get("estimated_spend_rub"),
        "models_scored": payload.get("models_scored"),
        "integration_errors": payload.get("integration_errors"),
        "rows": rows,
        "scientific_claim_boundary": payload.get("scientific_claim_boundary"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--expected-models", type=int, required=True)
    parser.add_argument("--issue", type=int, required=True)
    args = parser.parse_args()

    if args.result.exists():
        payload = json.loads(args.result.read_text(encoding="utf-8"))
    else:
        payload = {
            "experiment_id": None,
            "models_scored": 0,
            "estimated_spend_rub": 0,
            "integration_errors": ["result file missing"],
            "rows": [],
        }
    evidence = compact(payload)
    body = (
        f"## {args.label}\n\n"
        f"- workflow run: `{os.environ.get('GITHUB_RUN_ID')}`\n"
        f"- architecture SHA: `{os.environ.get('ACCB_ARCHITECTURE_SHA')}`\n"
        f"- expected models: `{args.expected_models}`\n"
        "- raw provider reasoning retained: `no`\n"
        "- scientific scope: integration/calibration gate, not threshold evidence\n\n"
        "```json\n" + json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2) + "\n```\n"
    )
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GH_TOKEN"]
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues/{args.issue}/comments",
        data=json.dumps({"body": body}, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        if response.status != 201:
            raise SystemExit(f"evidence publish failed: HTTP {response.status}")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(f"## {args.label}\n\n")
            handle.write(f"- models scored: `{evidence.get('models_scored')}` / `{args.expected_models}`\n")
            handle.write(f"- estimated spend: `{evidence.get('estimated_spend_rub')} RUB`\n")
            handle.write(f"- integration errors: `{len(evidence.get('integration_errors') or [])}`\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
