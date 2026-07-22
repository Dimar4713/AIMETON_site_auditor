#!/usr/bin/env python3
"""Guarded OpenStack soft reboot for the canonical stage VM.

Uses Application Credential authentication and direct Keystone/Nova endpoints.
Only Nova reboot type SOFT is implemented. No hard reboot, rebuild, rescue,
delete, stop, start, or resize operations exist in this client.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

DEFAULT_COMPUTE_ENDPOINT = "https://api.immers.cloud:8774/v2.1"
REQUEST_TIMEOUT_SECONDS = 30
POLL_SECONDS = 10


def _clean(value: str | None) -> str:
    cleaned = (value or "").strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _env(name: str, default: str | None = None) -> str:
    value = _clean(os.getenv(name, default))
    if not value:
        raise RuntimeError(f"Missing required OpenStack environment variable: {name}")
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _authenticate() -> tuple[str, str | None, str | None, str | None]:
    auth_url = _env("OS_AUTH_URL").rstrip("/")
    response = requests.post(
        f"{auth_url}/auth/tokens",
        json={
            "auth": {
                "identity": {
                    "methods": ["application_credential"],
                    "application_credential": {
                        "id": _env("OS_APPLICATION_CREDENTIAL_ID"),
                        "secret": _env("OS_APPLICATION_CREDENTIAL_SECRET"),
                    },
                }
            }
        },
        headers={"Accept": "application/json"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    token = response.headers.get("X-Subject-Token")
    if not token:
        raise RuntimeError("Keystone response did not include X-Subject-Token")
    body = response.json().get("token") or {}
    return (
        token,
        (body.get("project") or {}).get("id"),
        (body.get("user") or {}).get("id"),
        response.headers.get("X-Openstack-Request-Id"),
    )


def _server(compute: str, server_id: str, token: str) -> tuple[dict[str, Any], str | None]:
    response = requests.get(
        f"{compute}/servers/{server_id}",
        headers={"X-Auth-Token": token, "Accept": "application/json"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()["server"], response.headers.get("X-Openstack-Request-Id")


def main() -> int:
    parser = argparse.ArgumentParser(description="Guarded OpenStack SOFT reboot")
    parser.add_argument("--confirm-server-id", required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args()

    evidence: dict[str, Any] = {
        "operation": "openstack-soft-reboot",
        "actor": _clean(os.getenv("GITHUB_ACTOR")) or "unknown",
        "reason": args.reason.strip(),
        "started_at_utc": _utc_now(),
        "request_ids": {},
        "state_history": [],
    }

    try:
        canonical_id = _env("OPENSTACK_SERVER_ID")
        canonical_name = _env("OPENSTACK_SERVER_NAME")
        if args.confirm_server_id.strip() != canonical_id:
            raise RuntimeError("Server UUID confirmation does not match canonical OPENSTACK_SERVER_ID")
        if args.confirmation.strip() != "SOFT-REBOOT":
            raise RuntimeError("Confirmation phrase must be exactly SOFT-REBOOT")
        if len(args.reason.strip()) < 10:
            raise RuntimeError("Reason must contain at least 10 characters")

        compute = _env("OS_COMPUTE_ENDPOINT", DEFAULT_COMPUTE_ENDPOINT).rstrip("/")
        token, project_id, user_id, auth_request_id = _authenticate()
        evidence.update({"project_id": project_id, "user_id": user_id, "server_id": canonical_id})
        evidence["request_ids"]["keystone"] = auth_request_id

        before, before_request_id = _server(compute, canonical_id, token)
        evidence["request_ids"]["preflight"] = before_request_id
        evidence["preflight"] = {"name": before.get("name"), "status": before.get("status")}
        if before.get("name") != canonical_name:
            raise RuntimeError(f"Canonical server name mismatch: {before.get('name')!r}")
        if before.get("status") != "ACTIVE":
            raise RuntimeError(f"Server must be ACTIVE before soft reboot, got {before.get('status')!r}")

        reboot_response = requests.post(
            f"{compute}/servers/{canonical_id}/action",
            json={"reboot": {"type": "SOFT"}},
            headers={"X-Auth-Token": token, "Accept": "application/json"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        reboot_response.raise_for_status()
        evidence["request_ids"]["soft_reboot"] = reboot_response.headers.get("X-Openstack-Request-Id")
        evidence["reboot_requested_at_utc"] = _utc_now()

        deadline = time.monotonic() + max(120, args.timeout_seconds)
        observed_transition = False
        final_server: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            current, request_id = _server(compute, canonical_id, token)
            status = current.get("status")
            evidence["state_history"].append(
                {"timestamp_utc": _utc_now(), "status": status, "request_id": request_id}
            )
            if status != "ACTIVE":
                observed_transition = True
            if observed_transition and status == "ACTIVE":
                final_server = current
                break
            time.sleep(POLL_SECONDS)

        if final_server is None:
            raise RuntimeError("Server did not complete a visible reboot cycle and return to ACTIVE before timeout")

        evidence["postflight"] = {
            "name": final_server.get("name"),
            "status": final_server.get("status"),
        }
        evidence["completed_at_utc"] = _utc_now()
        evidence["result"] = "success"
    except Exception as exc:  # noqa: BLE001
        evidence["completed_at_utc"] = _utc_now()
        evidence["result"] = "failure"
        evidence["error"] = str(exc)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"OpenStack soft reboot failed: {exc}", file=sys.stderr)
        return 1

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": "success", "server_id": evidence["server_id"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
