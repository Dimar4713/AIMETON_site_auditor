#!/usr/bin/env python3
"""Review and safely delete quarantined archived branches.

The script is designed for GitHub Actions. It keeps a durable first-seen ledger,
produces a deterministic deletion manifest, and applies only an explicitly
confirmed manifest digest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ARCHIVE_PREFIX = "archiv_"
DEFAULT_PROTECTED = (
    "main",
    "master",
    "develop",
    "release/",
    "hotfix/",
    "security/",
    "archive-snapshot/",
)


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, text=True, capture_output=True)


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def list_remote_branches() -> dict[str, str]:
    result = run("git", "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/remotes/origin")
    branches: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        ref, sha = line.split(maxsplit=1)
        if ref == "origin/HEAD":
            continue
        name = ref.removeprefix("origin/")
        branches[name] = sha
    return branches


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(data: Any) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def safe_tag_component(branch: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", branch).strip("-")
    return value[:120] or "branch"


def is_ancestor(sha: str, base_ref: str) -> bool:
    completed = run("git", "merge-base", "--is-ancestor", sha, base_ref, check=False)
    return completed.returncode == 0


def build_plan(
    branches: dict[str, str],
    ledger: dict[str, Any],
    open_pr_heads: set[str],
    quarantine_days: int,
    protected_patterns: tuple[str, ...],
    now: datetime,
) -> tuple[dict[str, Any], dict[str, Any]]:
    records = ledger.setdefault("branches", {})
    candidates: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []

    for name, sha in sorted(branches.items()):
        if not name.startswith(ARCHIVE_PREFIX):
            continue
        record = records.setdefault(
            name,
            {"first_seen_archived_at": iso(now), "first_seen_sha": sha, "last_seen_sha": sha},
        )
        record["last_seen_sha"] = sha
        record["last_seen_at"] = iso(now)

        reason = None
        if name in open_pr_heads:
            reason = "open_pr_head"
        elif any(name == pattern or name.startswith(pattern) for pattern in protected_patterns):
            reason = "protected_pattern"
        else:
            first_seen = parse_iso(record["first_seen_archived_at"])
            eligible_at = first_seen + timedelta(days=quarantine_days)
            if now < eligible_at:
                reason = f"quarantine_until:{iso(eligible_at)}"

        if reason:
            excluded.append({"branch": name, "sha": sha, "reason": reason})
            continue

        reachable = is_ancestor(sha, "origin/main")
        tag = None if reachable else f"archive-snapshot/{safe_tag_component(name)}/{now.date().isoformat()}"
        candidates.append(
            {
                "branch": name,
                "sha": sha,
                "reachable_from_main": reachable,
                "snapshot_tag": tag,
                "first_seen_archived_at": record["first_seen_archived_at"],
            }
        )

    ledger["schema_version"] = "1.0"
    ledger["updated_at"] = iso(now)
    plan = {
        "schema_version": "1.0",
        "generated_at": iso(now),
        "quarantine_days": quarantine_days,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "excluded": excluded,
    }
    plan["manifest_digest"] = digest(plan)
    return ledger, plan


def apply_plan(plan: dict[str, Any], confirmation: str) -> list[dict[str, str]]:
    expected = f"DELETE ARCHIVED BRANCHES {plan['manifest_digest']}"
    if confirmation != expected:
        raise RuntimeError(f"Confirmation mismatch. Expected exact string: {expected}")

    results: list[dict[str, str]] = []
    for item in plan["candidates"]:
        branch = item["branch"]
        sha = item["sha"]
        current = run("git", "ls-remote", "origin", f"refs/heads/{branch}").stdout.strip()
        if not current or current.split()[0] != sha:
            raise RuntimeError(f"Branch changed or missing before deletion: {branch}")

        tag = item.get("snapshot_tag")
        if tag:
            run("git", "tag", "-a", tag, sha, "-m", f"Snapshot before deleting {branch}")
            run("git", "push", "origin", f"refs/tags/{tag}")
            tagged = run("git", "ls-remote", "origin", f"refs/tags/{tag}^{{}}").stdout.strip()
            if not tagged or tagged.split()[0] != sha:
                raise RuntimeError(f"Snapshot tag verification failed: {tag}")

        run("git", "push", "origin", "--delete", branch)
        remaining = run("git", "ls-remote", "origin", f"refs/heads/{branch}").stdout.strip()
        if remaining:
            raise RuntimeError(f"Branch still exists after deletion: {branch}")
        results.append({"branch": branch, "sha": sha, "snapshot_tag": tag or ""})
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("review", "apply"), default="review")
    parser.add_argument("--ledger", default="docs/governance/branch-archive-ledger.json")
    parser.add_argument("--plan", default="artifacts/archived-branch-plan.json")
    parser.add_argument("--result", default="artifacts/archived-branch-result.json")
    parser.add_argument("--quarantine-days", type=int, default=30)
    parser.add_argument("--open-pr-heads-json", default="[]")
    parser.add_argument("--confirmation", default="")
    args = parser.parse_args()

    run("git", "fetch", "origin", "+refs/heads/*:refs/remotes/origin/*", "--prune")
    branches = list_remote_branches()
    ledger_path = Path(args.ledger)
    plan_path = Path(args.plan)
    result_path = Path(args.result)
    ledger = load_json(ledger_path, {"schema_version": "1.0", "branches": {}})
    open_pr_heads = set(json.loads(args.open_pr_heads_json))
    now = utc_now()
    ledger, plan = build_plan(
        branches,
        ledger,
        open_pr_heads,
        args.quarantine_days,
        DEFAULT_PROTECTED,
        now,
    )

    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    result: dict[str, Any] = {"mode": args.mode, "manifest_digest": plan["manifest_digest"]}
    if args.mode == "apply":
        result["deleted"] = apply_plan(plan, args.confirmation)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"candidate_count": plan["candidate_count"], "manifest_digest": plan["manifest_digest"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
