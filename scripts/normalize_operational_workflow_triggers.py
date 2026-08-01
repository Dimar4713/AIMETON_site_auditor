#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

TARGETS = [
    ".github/workflows/stage-retention.yml",
    ".github/workflows/stage-observability.yml",
    ".github/workflows/project-governance-audit.yml",
    ".github/workflows/openstack-recovery-plan-auto.yml",
    ".github/workflows/mcp-security-acceptance.yml",
    ".github/workflows/project-actual-dates-apply.yml",
    ".github/workflows/project-actual-dates-backfill.yml",
    ".github/workflows/project-legacy-debt-transfer.yml",
    ".github/workflows/project-historical-exceptions-apply.yml",
]


def remove_issues_trigger(text: str) -> tuple[str, bool]:
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    in_on = False
    skipping = False
    changed = False
    has_dispatch = False

    for line in lines:
        stripped = line.strip()
        if line.startswith("on:"):
            in_on = True
            out.append(line)
            continue
        if in_on and line and not line.startswith((" ", "\t", "\n", "\r")):
            in_on = False
            skipping = False
        if in_on and line.startswith("  workflow_dispatch:"):
            has_dispatch = True
        if in_on and line.startswith("  issues:"):
            skipping = True
            changed = True
            continue
        if skipping:
            if line.startswith("  ") and not line.startswith("    ") and stripped:
                skipping = False
            else:
                continue
        out.append(line)

    result = "".join(out)
    if changed and not has_dispatch:
        marker = "on:\n"
        if marker not in result:
            raise RuntimeError("top-level on block not found")
        result = result.replace(marker, marker + "  workflow_dispatch:\n", 1)
    return result, changed


def main() -> int:
    changed_paths: list[str] = []
    for raw in TARGETS:
        path = Path(raw)
        if not path.exists():
            raise SystemExit(f"missing target: {raw}")
        original = path.read_text(encoding="utf-8")
        updated, changed = remove_issues_trigger(original)
        if changed:
            path.write_text(updated, encoding="utf-8")
            changed_paths.append(raw)

    for raw in TARGETS:
        text = Path(raw).read_text(encoding="utf-8")
        on_prefix = text.split("permissions:", 1)[0]
        if "  issues:" in on_prefix:
            raise SystemExit(f"issues trigger remains: {raw}")
        if "workflow_dispatch:" not in on_prefix and "schedule:" not in on_prefix and "workflow_run:" not in on_prefix:
            raise SystemExit(f"no explicit trigger remains: {raw}")

    print("normalized_count=" + str(len(changed_paths)))
    for path in changed_paths:
        print("normalized=" + path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
