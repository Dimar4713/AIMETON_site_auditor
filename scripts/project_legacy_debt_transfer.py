#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

MANIFEST = Path("config/project_legacy_debt_transfer.json")
EXPECTED = {10,11,12,13,14,15,16,28,31,32,34,36,40,50,64,65,80,82,83,85,95,126}
HEADING = "## Debt transfer"


def desired_body(body: str, registry: int) -> str:
    marker = f"Historical checklist/evidence debt is tracked in #{registry}."
    if HEADING in body and marker in body:
        return body
    suffix = f"\n\n{HEADING}\n\n{marker}\nNo existing checkbox was changed automatically.\n"
    return body.rstrip() + suffix


def request(url: str, token: str, method: str = "GET", payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(req) as response:
        return json.load(response)


def main() -> None:
    token = os.environ["GH_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    manifest = json.loads(MANIFEST.read_text())
    items = set(manifest["items"])
    if items != EXPECTED:
        raise RuntimeError("Unexpected legacy debt allowlist")
    registry = int(manifest["registry_issue"])
    planned = []
    snapshots = {}
    for number in sorted(items):
        issue = request(f"https://api.github.com/repos/{repo}/issues/{number}", token)
        before = issue.get("body") or ""
        after = desired_body(before, registry)
        snapshots[number] = after
        if after != before:
            planned.append(number)
    if os.environ.get("APPLY") != "true":
        print(json.dumps({"mode":"dry_run","planned":planned,"count":len(planned)}, indent=2))
        return
    for number in planned:
        request(f"https://api.github.com/repos/{repo}/issues/{number}", token, "PATCH", {"body": snapshots[number]})
    errors = []
    for number in sorted(items):
        issue = request(f"https://api.github.com/repos/{repo}/issues/{number}", token)
        if desired_body(issue.get("body") or "", registry) != (issue.get("body") or ""):
            errors.append(number)
    print(json.dumps({"mode":"apply","mutations":len(planned),"readback_errors":errors,"success":not errors}, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
