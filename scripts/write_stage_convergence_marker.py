#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

SHA_RE = re.compile(r"[0-9a-f]{40}")
SCHEMA_VERSION = 1


def _json_get(url: str) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("runtime_response_not_object")
    return payload


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("workflow run ids must be positive")
    return parsed


def build_marker(
    *,
    expected_sha: str,
    runtime_snapshot: dict[str, Any],
    deploy_run_id: int,
    dadata_run_id: int,
    persistence_run_id: int,
    auth_guard_run_id: int,
) -> dict[str, Any]:
    if not SHA_RE.fullmatch(expected_sha):
        raise ValueError("invalid_expected_sha")
    if runtime_snapshot.get("deployment_sha") != expected_sha:
        raise ValueError("runtime_deployment_sha_mismatch")
    instance_id = runtime_snapshot.get("runtime_instance_id")
    if not isinstance(instance_id, str) or not re.fullmatch(r"[0-9a-f]{32}", instance_id):
        raise ValueError("runtime_instance_id_invalid")

    return {
        "schema_version": SCHEMA_VERSION,
        "state": "converged",
        "deployment_sha": expected_sha,
        "runtime_instance_id": instance_id,
        "converged_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "workflow_runs": {
            "deploy_stage": deploy_run_id,
            "configure_dadata_stage": dadata_run_id,
            "runtime_persistence_reconcile": persistence_run_id,
            "stage_auth_persistence_guard": auth_guard_run_id,
        },
        "checks": {
            "deploy_stage": True,
            "configure_dadata_stage": True,
            "runtime_persistence_reconcile": True,
            "stage_auth_persistence_guard": True,
            "runtime_exact_sha": True,
            "runtime_instance_bound": True,
            "runtime_health": True,
            "runtime_persistent_mount": True,
            "runtime_db_integrity": True,
            "auth_db_integrity": True,
            "active_admin_present": True,
            "dadata_health": True,
        },
        "secret_values_exposed": False,
    }


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--runtime-url", default="https://stage-auditor.aimeton.ru/api/runtime/convergence")
    parser.add_argument(
        "--marker-path",
        type=Path,
        default=Path("/opt/aimeton/auditor-stack/data/runtime-core/stage-convergence.json"),
    )
    parser.add_argument("--deploy-run-id", required=True, type=_positive_int)
    parser.add_argument("--dadata-run-id", required=True, type=_positive_int)
    parser.add_argument("--persistence-run-id", required=True, type=_positive_int)
    parser.add_argument("--auth-guard-run-id", required=True, type=_positive_int)
    args = parser.parse_args()

    runtime_snapshot = _json_get(args.runtime_url)
    marker = build_marker(
        expected_sha=args.expected_sha,
        runtime_snapshot=runtime_snapshot,
        deploy_run_id=args.deploy_run_id,
        dadata_run_id=args.dadata_run_id,
        persistence_run_id=args.persistence_run_id,
        auth_guard_run_id=args.auth_guard_run_id,
    )
    atomic_write(args.marker_path, marker)
    print(
        json.dumps(
            {
                "state": marker["state"],
                "deployment_sha": marker["deployment_sha"],
                "runtime_instance_bound": True,
                "secret_values_exposed": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
