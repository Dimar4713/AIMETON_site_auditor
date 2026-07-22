#!/usr/bin/env python3
"""Read-only OpenStack inventory for immers.cloud.

Authentication uses an Application Credential through Keystone's token API.
Provider APIs are queried through known HTTPS endpoints, so inventory does not
depend on the Keystone service catalog. The script performs no mutating operation.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from typing import Any

import requests

DEFAULT_COMPUTE_ENDPOINT = "https://api.immers.cloud:8774/v2.1"
DEFAULT_NETWORK_ENDPOINT = "https://api.immers.cloud:9696/v2.0"
DEFAULT_BLOCK_STORAGE_ENDPOINT = "https://api.immers.cloud:8776/v3"
REQUEST_TIMEOUT_SECONDS = 30


@dataclass
class Inventory:
    project_id: str | None
    user_id: str | None
    servers: list[dict[str, Any]]
    volumes: list[dict[str, Any]]
    ports: list[dict[str, Any]]
    security_groups: list[dict[str, Any]]
    scope: str


def _require_application_credential() -> None:
    required = [
        "OS_AUTH_URL",
        "OS_APPLICATION_CREDENTIAL_ID",
        "OS_APPLICATION_CREDENTIAL_SECRET",
    ]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            "Missing required OpenStack environment variables: " + ", ".join(missing)
        )


def _authenticated_context() -> tuple[str, str | None, str | None]:
    auth_url = os.environ["OS_AUTH_URL"].rstrip("/")
    token_url = f"{auth_url}/auth/tokens"
    payload = {
        "auth": {
            "identity": {
                "methods": ["application_credential"],
                "application_credential": {
                    "id": os.environ["OS_APPLICATION_CREDENTIAL_ID"],
                    "secret": os.environ["OS_APPLICATION_CREDENTIAL_SECRET"],
                },
            }
        }
    }
    response = requests.post(
        token_url,
        json=payload,
        headers={"Accept": "application/json"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    token = response.headers.get("X-Subject-Token")
    if not token:
        raise RuntimeError("Keystone response did not include X-Subject-Token")
    body = response.json()
    token_body = body.get("token") or {}
    project_id = (token_body.get("project") or {}).get("id")
    user_id = (token_body.get("user") or {}).get("id")
    return token, project_id, user_id


def _get_json(url: str, token: str) -> dict[str, Any]:
    response = requests.get(
        url,
        headers={"X-Auth-Token": token, "Accept": "application/json"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected JSON payload from {url}")
    return payload


def _server_record(server: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": server.get("id"),
        "name": server.get("name"),
        "status": server.get("status"),
        "addresses": server.get("addresses") or {},
        "flavor": server.get("flavor"),
        "metadata": server.get("metadata") or {},
        "created_at": server.get("created") or "",
        "updated_at": server.get("updated") or "",
    }


def collect_inventory(*, compute_only: bool = False) -> Inventory:
    _require_application_credential()
    token, project_id, user_id = _authenticated_context()

    compute_endpoint = os.getenv("OS_COMPUTE_ENDPOINT", DEFAULT_COMPUTE_ENDPOINT).rstrip("/")
    compute_payload = _get_json(f"{compute_endpoint}/servers/detail", token)
    servers = [_server_record(item) for item in compute_payload.get("servers", [])]

    if compute_only:
        return Inventory(
            project_id=project_id,
            user_id=user_id,
            servers=servers,
            volumes=[],
            ports=[],
            security_groups=[],
            scope="compute-only-direct-endpoints",
        )

    if not project_id:
        raise RuntimeError("Application Credential token did not expose project_id")

    network_endpoint = os.getenv("OS_NETWORK_ENDPOINT", DEFAULT_NETWORK_ENDPOINT).rstrip("/")
    block_endpoint = os.getenv(
        "OS_BLOCK_STORAGE_ENDPOINT", DEFAULT_BLOCK_STORAGE_ENDPOINT
    ).rstrip("/")

    volume_payload = _get_json(
        f"{block_endpoint}/{project_id}/volumes/detail", token
    )
    volumes = [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "status": item.get("status"),
            "size_gb": item.get("size"),
            "attachments": item.get("attachments") or [],
        }
        for item in volume_payload.get("volumes", [])
    ]

    port_payload = _get_json(f"{network_endpoint}/ports", token)
    ports = [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "status": item.get("status"),
            "network_id": item.get("network_id"),
            "device_id": item.get("device_id"),
            "fixed_ips": item.get("fixed_ips") or [],
            "security_group_ids": item.get("security_groups") or [],
        }
        for item in port_payload.get("ports", [])
    ]

    group_payload = _get_json(f"{network_endpoint}/security-groups", token)
    security_groups = [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "description": item.get("description"),
            "project_id": item.get("project_id") or item.get("tenant_id"),
        }
        for item in group_payload.get("security_groups", [])
    ]

    return Inventory(
        project_id=project_id,
        user_id=user_id,
        servers=servers,
        volumes=volumes,
        ports=ports,
        security_groups=security_groups,
        scope="full-direct-endpoints",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only OpenStack inventory")
    parser.add_argument("--output", help="Optional JSON output file")
    parser.add_argument(
        "--compute-only",
        action="store_true",
        help="Query only Keystone and Nova; suitable for deployment preflight/postflight",
    )
    args = parser.parse_args()

    try:
        payload = asdict(collect_inventory(compute_only=args.compute_only))
    except Exception as exc:  # noqa: BLE001
        print(f"OpenStack inventory failed: {exc}", file=sys.stderr)
        return 1

    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(rendered + "\n")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
