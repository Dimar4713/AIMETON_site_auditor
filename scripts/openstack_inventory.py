#!/usr/bin/env python3
"""Read-only OpenStack inventory for immers.cloud.

Authentication uses standard OpenStack environment variables, preferably an
Application Credential. The script performs no mutating operation.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from typing import Any

import openstack


DEFAULT_COMPUTE_ENDPOINT = "https://api.immers.cloud:8774/v2.1"
DEFAULT_NETWORK_ENDPOINT = "https://api.immers.cloud:9696/v2.0"
DEFAULT_BLOCK_STORAGE_ENDPOINT = "https://api.immers.cloud:8776/v3"


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


def _server_record(server: Any) -> dict[str, Any]:
    return {
        "id": server.id,
        "name": server.name,
        "status": server.status,
        "addresses": server.addresses,
        "flavor": getattr(server, "flavor", None),
        "metadata": getattr(server, "metadata", None) or {},
        "created_at": str(getattr(server, "created_at", "") or ""),
        "updated_at": str(getattr(server, "updated_at", "") or ""),
    }


def collect_inventory(*, compute_only: bool = False) -> Inventory:
    _require_application_credential()
    connect_kwargs: dict[str, Any] = {
        "auth_type": "v3applicationcredential",
        "auth_url": os.environ["OS_AUTH_URL"],
        "application_credential_id": os.environ["OS_APPLICATION_CREDENTIAL_ID"],
        "application_credential_secret": os.environ["OS_APPLICATION_CREDENTIAL_SECRET"],
        "verify": True,
        # immers.cloud CLI access is known to work with these native endpoints.
        # Explicit overrides avoid provider catalog inconsistencies on SDK discovery.
        "compute_endpoint_override": os.getenv(
            "OS_COMPUTE_ENDPOINT", DEFAULT_COMPUTE_ENDPOINT
        ),
    }
    region_name = os.getenv("OS_REGION_NAME")
    if region_name:
        connect_kwargs["region_name"] = region_name

    if not compute_only:
        connect_kwargs["network_endpoint_override"] = os.getenv(
            "OS_NETWORK_ENDPOINT", DEFAULT_NETWORK_ENDPOINT
        )
        connect_kwargs["block_storage_endpoint_override"] = os.getenv(
            "OS_BLOCK_STORAGE_ENDPOINT", DEFAULT_BLOCK_STORAGE_ENDPOINT
        )

    conn = openstack.connect(**connect_kwargs)

    auth = conn.session.auth
    project_id = getattr(auth, "get_project_id", lambda _session: None)(conn.session)
    user_id = getattr(auth, "get_user_id", lambda _session: None)(conn.session)

    servers = [_server_record(server) for server in conn.compute.servers(details=True)]

    if compute_only:
        return Inventory(
            project_id=project_id,
            user_id=user_id,
            servers=servers,
            volumes=[],
            ports=[],
            security_groups=[],
            scope="compute-only",
        )

    volumes = [
        {
            "id": volume.id,
            "name": volume.name,
            "status": volume.status,
            "size_gb": volume.size,
            "attachments": getattr(volume, "attachments", None) or [],
        }
        for volume in conn.block_storage.volumes(details=True)
    ]
    ports = [
        {
            "id": port.id,
            "name": port.name,
            "status": port.status,
            "network_id": port.network_id,
            "device_id": port.device_id,
            "fixed_ips": port.fixed_ips,
            "security_group_ids": port.security_group_ids,
        }
        for port in conn.network.ports()
    ]
    security_groups = [
        {
            "id": group.id,
            "name": group.name,
            "description": group.description,
            "project_id": group.project_id,
        }
        for group in conn.network.security_groups()
    ]

    return Inventory(
        project_id=project_id,
        user_id=user_id,
        servers=servers,
        volumes=volumes,
        ports=ports,
        security_groups=security_groups,
        scope="full",
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
