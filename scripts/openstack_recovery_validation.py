#!/usr/bin/env python3
"""Guarded OpenStack recovery validation lifecycle.

Modes:
- plan: validate image/flavor/network and emit a non-mutating plan;
- create: create only an isolated server named aimeton-validation-*;
- delete: delete only an explicitly confirmed aimeton-validation-* server.

The configured canonical production/stage server is never modified.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import openstack

VALIDATION_PREFIX = "aimeton-validation-"
NAME_RE = re.compile(r"^aimeton-validation-[a-z0-9][a-z0-9-]{2,48}$")


def clean(value: str | None) -> str:
    value = (value or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    return value


def env(name: str, default: str = "") -> str:
    value = clean(os.getenv(name, default))
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def connection() -> openstack.connection.Connection:
    return openstack.connect(
        auth_url=env("OS_AUTH_URL"),
        application_credential_id=env("OS_APPLICATION_CREDENTIAL_ID"),
        application_credential_secret=env("OS_APPLICATION_CREDENTIAL_SECRET"),
        auth_type="v3applicationcredential",
    )


def write_json(path: str, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def base_evidence(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "actor": clean(os.getenv("GITHUB_ACTOR")),
        "mode": args.mode,
        "reason": args.reason,
        "canonical_server_id": clean(os.getenv("OPENSTACK_SERVER_ID")),
        "validation_name": args.validation_name,
    }


def require_validation_name(name: str) -> None:
    if not NAME_RE.fullmatch(name):
        raise RuntimeError("Validation server name must match aimeton-validation-[a-z0-9-]")


def resolve_create_inputs(conn: openstack.connection.Connection, args: argparse.Namespace) -> tuple[Any, Any, Any]:
    image = conn.image.get_image(args.image_id)
    if not image:
        raise RuntimeError(f"Snapshot image not found: {args.image_id}")
    if str(image.status).lower() != "active":
        raise RuntimeError(f"Snapshot image is not active: {image.status}")
    flavor = conn.compute.find_flavor(args.flavor, ignore_missing=False)
    network = conn.network.find_network(args.network, ignore_missing=False)
    return image, flavor, network


def main() -> int:
    parser = argparse.ArgumentParser(description="Guarded OpenStack recovery validation")
    parser.add_argument("--mode", choices=["plan", "create", "delete"], required=True)
    parser.add_argument("--validation-name", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--image-id", default="")
    parser.add_argument("--flavor", default="")
    parser.add_argument("--network", default="")
    parser.add_argument("--security-group", action="append", default=[])
    parser.add_argument("--key-name", default="")
    parser.add_argument("--server-id", default="")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--wait-seconds", type=int, default=900)
    args = parser.parse_args()

    try:
        require_validation_name(args.validation_name)
        if len(args.reason.strip()) < 8:
            raise RuntimeError("Reason must contain at least 8 characters")
        canonical_id = env("OPENSTACK_SERVER_ID")
        conn = connection()
        evidence = base_evidence(args)

        if args.mode in {"plan", "create"}:
            if not args.image_id or not args.flavor or not args.network:
                raise RuntimeError("image-id, flavor and network are required for plan/create")
            image, flavor, network = resolve_create_inputs(conn, args)
            existing = conn.compute.find_server(args.validation_name, ignore_missing=True)
            if existing:
                raise RuntimeError(f"Validation server name already exists: {args.validation_name}")
            evidence["source_image"] = {
                "id": image.id,
                "name": image.name,
                "status": image.status,
                "created_at": str(getattr(image, "created_at", "")),
            }
            evidence["requested_resources"] = {
                "flavor_id": flavor.id,
                "flavor_name": flavor.name,
                "network_id": network.id,
                "network_name": network.name,
                "security_groups": sorted(args.security_group),
                "key_name_configured": bool(args.key_name),
            }
            if args.mode == "plan":
                evidence["result"] = "validated_no_changes"
                write_json(args.output, evidence)
                print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
                return 0
            if args.confirm != f"CREATE {args.validation_name}":
                raise RuntimeError(f"Create confirmation must equal: CREATE {args.validation_name}")

            create_args: dict[str, Any] = {
                "name": args.validation_name,
                "image_id": image.id,
                "flavor_id": flavor.id,
                "networks": [{"uuid": network.id}],
                "metadata": {
                    "aimeton_purpose": "snapshot-recovery-validation",
                    "aimeton_source_image": image.id,
                    "aimeton_actor": clean(os.getenv("GITHUB_ACTOR"))[:255],
                },
            }
            if args.security_group:
                create_args["security_groups"] = [{"name": name} for name in args.security_group]
            if args.key_name:
                create_args["key_name"] = args.key_name

            server = conn.compute.create_server(**create_args)
            server = conn.compute.wait_for_server(server, status="ACTIVE", failures=["ERROR"], wait=args.wait_seconds)
            if server.id == canonical_id:
                raise RuntimeError("Invariant violation: validation server equals canonical server")
            evidence["validation_server"] = {
                "id": server.id,
                "name": server.name,
                "status": server.status,
                "created_at": str(getattr(server, "created_at", "")),
            }
            evidence["result"] = "validation_server_created"
            write_json(args.output, evidence)
            print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
            return 0

        if not args.server_id:
            raise RuntimeError("server-id is required for delete")
        if args.server_id == canonical_id:
            raise RuntimeError("Refusing to delete canonical server")
        server = conn.compute.get_server(args.server_id)
        if not server:
            raise RuntimeError(f"Validation server not found: {args.server_id}")
        if server.name != args.validation_name or not server.name.startswith(VALIDATION_PREFIX):
            raise RuntimeError("Server identity/prefix does not match guarded validation resource")
        if args.confirm != f"DELETE {args.server_id}":
            raise RuntimeError(f"Delete confirmation must equal: DELETE {args.server_id}")
        conn.compute.delete_server(server, ignore_missing=False)
        conn.compute.wait_for_delete(server, wait=args.wait_seconds)
        evidence["validation_server"] = {"id": args.server_id, "name": server.name, "status": "DELETED"}
        evidence["result"] = "validation_server_deleted"
        write_json(args.output, evidence)
        print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"OpenStack recovery validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
