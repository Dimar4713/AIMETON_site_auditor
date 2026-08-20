from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def _request_json(url: str, token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "aimeton-parent-job-gate",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"github_api_http_{exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("github_api_unavailable") from exc


def list_parent_jobs(repository: str, run_id: int, token: str) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for page in range(1, 11):
        query = urllib.parse.urlencode({"per_page": 100, "page": page})
        payload = _request_json(
            f"https://api.github.com/repos/{repository}/actions/runs/{run_id}/jobs?{query}",
            token,
        )
        page_jobs = list(payload.get("jobs") or [])
        jobs.extend(page_jobs)
        if len(page_jobs) < 100:
            break
    return jobs


def parent_job_succeeded(jobs: list[dict[str, Any]], job_name: str) -> bool:
    return any(
        str(item.get("name") or "") == job_name
        and item.get("status") == "completed"
        and item.get("conclusion") == "success"
        for item in jobs
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--parent-run-id", default="")
    parser.add_argument("--job-name", required=True)
    parser.add_argument("--allow-manual", action="store_true")
    args = parser.parse_args()

    if args.event_name == "workflow_dispatch" and args.allow_manual:
        print("manual_dispatch_admitted")
        return 0

    try:
        run_id = int(args.parent_run_id)
    except ValueError:
        print("invalid_parent_run_id", file=sys.stderr)
        return 1
    if run_id <= 0:
        print("invalid_parent_run_id", file=sys.stderr)
        return 1

    token = os.getenv("GITHUB_TOKEN", "")
    if not token:
        print("missing_github_token", file=sys.stderr)
        return 2
    try:
        jobs = list_parent_jobs(args.repository, run_id, token)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if not parent_job_succeeded(jobs, args.job_name):
        print(f"required_parent_job_not_successful:{args.job_name}", file=sys.stderr)
        return 1
    print(f"required_parent_job_successful:{args.job_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
