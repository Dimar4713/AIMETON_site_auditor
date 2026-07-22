#!/usr/bin/env python3
"""Create a guarded OpenStack server snapshot through direct Keystone/Nova/Glance APIs.

This script performs one write operation only: Nova createImage for the configured
server UUID. It never deletes images, servers, volumes, or ports.
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
from urllib.parse import urlparse

import requests

DEFAULT_COMPUTE_ENDPOINT = "https://api.immers.cloud:8774/v2.1"
DEFAULT_IMAGE_ENDPOINT = "https://api.immers.cloud:9292/v2"
REQUEST_TIMEOUT_SECONDS = 30


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


def _auth_token() -> tuple[str, str | None, str | None, str | None]:
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


def _headers(token: str) -> dict[str, str]:
    return {"X-Auth-Token": token, "Accept": "application/json"}


def _get_server(token: str, endpoint: str, server_id: str) -> tuple[dict[str, Any], str | None]:
    response = requests.get(
        f"{endpoint.rstrip('/')}/servers/{server_id}",
        headers=_headers(token),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json().get("server") or {}, response.headers.get("X-Openstack-Request-Id")


def _image_id_from_location(location: str | None) -> str:
    if not location:
        raise RuntimeError("Nova createImage response did not include Location header")
    path = urlparse(location).path.rstrip("/")
    image_id = path.rsplit("/", 1)[-1]
    if len(image_id) < 32:
        raise RuntimeError(f"Unexpected image location: {location}")
    return image_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Guarded OpenStack snapshot creator")
    parser.add_argument("--server-id", required=True)
    parser.add_argument("--expected-name", required=True)
    parser.add_argument("--confirm-server-id", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--snapshot-name", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--wait-seconds", type=int, default=1800)
    args = parser.parse_args()

    try:
        if args.confirm_server_id != args.server_id:
            raise RuntimeError("Confirmation UUID does not match configured server UUID")
        if len(args.reason.strip()) < 8:
            raise RuntimeError("Snapshot reason must contain at least 8 characters")
        if not args.snapshot_name.startswith("aimeton-main-server-"):
            raise RuntimeError("Snapshot name must start with aimeton-main-server-")

        token, project_id, user_id, auth_request_id = _auth_token()
        compute_endpoint = _env("OS_COMPUTE_ENDPOINT", DEFAULT_COMPUTE_ENDPOINT)
        image_endpoint = _env("OS_IMAGE_ENDPOINT", DEFAULT_IMAGE_ENDPOINT)
        server, server_request_id = _get_server(token, compute_endpoint, args.server_id)

        if server.get("id") != args.server_id:
            raise RuntimeError("OpenStack returned a different server UUID")
        if server.get("name") != args.expected_name:
            raise RuntimeError(f"Unexpected server name: {server.get('name')}")
        if server.get("status") != "ACTIVE":
            raise RuntimeError(f"Server is not ACTIVE: {server.get('status')}")

        create_response = requests.post(
            f"{compute_endpoint.rstrip('/')}/servers/{args.server_id}/action",
            headers={**_headers(token), "Content-Type": "application/json"},
            json={"createImage": {"name": args.snapshot_name, "metadata": {"aimeton_reason": args.reason}}},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        create_response.raise_for_status()
        image_id = _image_id_from_location(create_response.headers.get("Location"))
        create_request_id = create_response.headers.get("X-Openstack-Request-Id")

        deadline = time.monotonic() + max(60, args.wait_seconds)
        image: dict[str, Any] = {}
        image_request_id: str | None = None
        while time.monotonic() < deadline:
            image_response = requests.get(
                f"{image_endpoint.rstrip('/')}/images/{image_id}",
                headers=_headers(token),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            image_response.raise_for_status()
            image = image_response.json()
            image_request_id = image_response.headers.get("X-Openstack-Request-Id")
            status = str(image.get("status") or "").lower()
            if status == "active":
                break
            if status in {"killed", "deleted", "deactivated"}:
                raise RuntimeError(f"Snapshot entered terminal state: {status}")
            time.sleep(10)
        else:
            raise RuntimeError(f"Timed out waiting for image {image_id} to become active")

        evidence = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "actor": _clean(os.getenv("GITHUB_ACTOR")),
            "reason": args.reason,
            "project_id": project_id,
            "user_id": user_id,
            "server": {"id": server.get("id"), "name": server.get("name"), "status": server.get("status")},
            "snapshot": {
                "id": image_id,
                "name": image.get("name"),
                "status": image.get("status"),
                "size": image.get("size"),
                "created_at": image.get("created_at"),
            },
            "request_ids": {
                "keystone": auth_request_id,
                "server_get": server_request_id,
                "create_image": create_request_id,
                "image_get": image_request_id,
            },
        }
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"OpenStack snapshot failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
