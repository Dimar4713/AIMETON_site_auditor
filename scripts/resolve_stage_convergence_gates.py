from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_REQUIRED_WORKFLOWS = (
    "Deploy Stage",
    "Configure DaData Stage",
    "Runtime Persistence Reconcile",
    "Stage Auth Persistence Guard",
)


@dataclass(frozen=True)
class ConvergenceGates:
    sha: str
    deploy_run_id: int
    dadata_run_id: int
    persistence_run_id: int
    auth_guard_run_id: int


def resolve_target_sha(*, event_name: str, manual_sha: str, event_payload: dict[str, Any]) -> str:
    if event_name == "workflow_dispatch":
        target = manual_sha.strip()
    else:
        trigger = event_payload.get("workflow_run") or {}
        if (
            trigger.get("name") != "Deploy Stage"
            or trigger.get("conclusion") != "success"
            or trigger.get("head_branch") != "main"
        ):
            raise ValueError("automatic_convergence_requires_successful_main_deploy")
        target = str(trigger.get("head_sha") or "").strip()
    if not _SHA_RE.fullmatch(target):
        raise ValueError("invalid_exact_sha")
    return target


def _latest_successful(runs: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    candidates = [
        item for item in runs
        if item.get("name") == name
        and item.get("status") == "completed"
        and item.get("conclusion") == "success"
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: str(item.get("created_at") or ""))


def resolve_ready_gates(runs: list[dict[str, Any]], target_sha: str) -> ConvergenceGates | None:
    deploy = _latest_successful(runs, "Deploy Stage")
    if deploy is None:
        return None
    deploy_created = str(deploy.get("created_at") or "")

    def after_deploy(name: str) -> dict[str, Any] | None:
        candidates = [
            item for item in runs
            if item.get("name") == name
            and item.get("status") == "completed"
            and item.get("conclusion") == "success"
            and str(item.get("created_at") or "") >= deploy_created
        ]
        return max(candidates, key=lambda item: str(item.get("created_at") or "")) if candidates else None

    dadata = after_deploy("Configure DaData Stage")
    persistence = after_deploy("Runtime Persistence Reconcile")
    auth = after_deploy("Stage Auth Persistence Guard")
    if not (dadata and persistence and auth):
        return None
    return ConvergenceGates(
        sha=target_sha,
        deploy_run_id=int(deploy["id"]),
        dadata_run_id=int(dadata["id"]),
        persistence_run_id=int(persistence["id"]),
        auth_guard_run_id=int(auth["id"]),
    )


def _request_json(url: str, token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "aimeton-stage-convergence",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"github_api_http_{exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("github_api_unavailable") from exc


def list_runs_for_sha(repository: str, target_sha: str, token: str) -> list[dict[str, Any]]:
    all_runs: list[dict[str, Any]] = []
    for page in range(1, 11):
        query = urllib.parse.urlencode({"head_sha": target_sha, "per_page": 100, "page": page})
        payload = _request_json(
            f"https://api.github.com/repos/{repository}/actions/runs?{query}",
            token,
        )
        page_runs = list(payload.get("workflow_runs") or [])
        all_runs.extend(page_runs)
        if len(page_runs) < 100:
            break
    return all_runs


def wait_for_gates(*, repository: str, target_sha: str, token: str, timeout_seconds: int, poll_seconds: int) -> ConvergenceGates:
    deadline = time.monotonic() + timeout_seconds
    while True:
        runs = list_runs_for_sha(repository, target_sha, token)
        gates = resolve_ready_gates(runs, target_sha)
        if gates is not None:
            return gates
        if time.monotonic() >= deadline:
            present = {
                name: bool(_latest_successful(runs, name))
                for name in _REQUIRED_WORKFLOWS
            }
            raise TimeoutError(f"stage_convergence_gates_timeout:{json.dumps(present, sort_keys=True)}")
        time.sleep(poll_seconds)


def write_github_outputs(path: str, gates: ConvergenceGates) -> None:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"sha={gates.sha}\n")
        handle.write(f"deploy_run_id={gates.deploy_run_id}\n")
        handle.write(f"dadata_run_id={gates.dadata_run_id}\n")
        handle.write(f"persistence_run_id={gates.persistence_run_id}\n")
        handle.write(f"auth_guard_run_id={gates.auth_guard_run_id}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--event-path", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--manual-sha", default="")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--github-output", required=True)
    args = parser.parse_args()

    token = os.getenv("GITHUB_TOKEN", "")
    if not token:
        print("missing_github_token", file=sys.stderr)
        return 2
    payload = json.loads(Path(args.event_path).read_text(encoding="utf-8"))
    try:
        target_sha = resolve_target_sha(
            event_name=args.event_name,
            manual_sha=args.manual_sha,
            event_payload=payload,
        )
        gates = wait_for_gates(
            repository=args.repository,
            target_sha=target_sha,
            token=token,
            timeout_seconds=max(1, args.timeout_seconds),
            poll_seconds=max(1, args.poll_seconds),
        )
    except (ValueError, RuntimeError, TimeoutError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    write_github_outputs(args.github_output, gates)
    print(
        "required gates converged: "
        f"sha={gates.sha} deploy={gates.deploy_run_id} dadata={gates.dadata_run_id} "
        f"persistence={gates.persistence_run_id} auth={gates.auth_guard_run_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
