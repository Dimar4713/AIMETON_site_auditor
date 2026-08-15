from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from uuid import uuid4


_SCHEMA_VERSION = 1
_RUNTIME_INSTANCE_ID = uuid4().hex
_SHA_RE = re.compile(r"[0-9a-f]{40}")


def runtime_instance_id() -> str:
    """Return an opaque id that changes on every application process start."""
    return _RUNTIME_INSTANCE_ID


def deployment_sha() -> str | None:
    value = os.getenv("AIMETON_DEPLOY_SHA", "").strip()
    if not value:
        path = Path(".aimeton-deploy-sha")
        if path.is_file():
            value = path.read_text(encoding="utf-8").strip()
    return value if _SHA_RE.fullmatch(value) else None


def convergence_marker_path() -> Path:
    return Path(
        os.getenv(
            "AIMETON_STAGE_CONVERGENCE_MARKER",
            "data/stage-convergence.json",
        )
    )


def _safe_marker(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, "marker_missing"
    try:
        raw = path.read_text(encoding="utf-8")
        if len(raw) > 64_000:
            return None, "marker_too_large"
        payload = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, "marker_invalid"
    if not isinstance(payload, dict):
        return None, "marker_invalid"
    return payload, None


def runtime_convergence_snapshot() -> dict[str, Any]:
    """Project convergence state without exposing secrets or host internals.

    A persistent marker is considered valid only for the exact deployed source
    and the exact currently running application instance. Any restart/recreate
    changes the in-process instance id, which makes an old marker stale even
    though the persistent file survived the restart.
    """
    current_sha = deployment_sha()
    instance_id = runtime_instance_id()
    path = convergence_marker_path()
    marker, marker_error = _safe_marker(path)

    base: dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "state": "pending",
        "deployment_sha": current_sha,
        "runtime_instance_id": instance_id,
        "marker_present": marker is not None,
        "marker_error": marker_error,
        "secrets_exposed": False,
    }
    if marker is None:
        return base

    marker_sha = marker.get("deployment_sha")
    marker_instance = marker.get("runtime_instance_id")
    marker_state = marker.get("state")
    marker_schema = marker.get("schema_version")
    converged_at = marker.get("converged_at_utc")

    base.update(
        {
            "marker_deployment_sha": marker_sha if isinstance(marker_sha, str) else None,
            "marker_runtime_instance_id": (
                marker_instance if isinstance(marker_instance, str) else None
            ),
            "converged_at_utc": converged_at if isinstance(converged_at, str) else None,
        }
    )

    if marker_schema != _SCHEMA_VERSION or marker_state != "converged":
        base["state"] = "invalid"
        base["marker_error"] = "marker_contract_mismatch"
        return base
    if current_sha is None or marker_sha != current_sha:
        base["state"] = "stale"
        base["marker_error"] = "deployment_sha_mismatch"
        return base
    if marker_instance != instance_id:
        base["state"] = "stale"
        base["marker_error"] = "runtime_instance_mismatch"
        return base

    required_checks = marker.get("checks")
    if not isinstance(required_checks, dict) or not required_checks:
        base["state"] = "invalid"
        base["marker_error"] = "checks_missing"
        return base
    if not all(value is True for value in required_checks.values()):
        base["state"] = "invalid"
        base["marker_error"] = "checks_incomplete"
        return base

    base["state"] = "converged"
    base["marker_error"] = None
    base["checks"] = sorted(required_checks)
    return base
