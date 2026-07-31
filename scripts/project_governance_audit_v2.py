#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

from scripts.project_governance_audit import audit_item, load_items, project_id

MANIFEST = Path("config/project_historical_exceptions.json")
DATE_CODES = {
    "active_without_actual_start",
    "completed_without_actual_finish",
    "actual_finish_without_start",
    "actual_finish_before_start",
}


def main() -> None:
    token = os.environ["GH_TOKEN"]
    owner = os.environ["PROJECT_OWNER"]
    number = int(os.environ["PROJECT_NUMBER"])
    exclusions = {
        int(value)
        for value in json.loads(MANIFEST.read_text(encoding="utf-8"))["lifecycle_exclusions"]
    }
    items = load_items(token, project_id(token, owner, number))
    findings = []
    for item in items:
        content = item.get("content") or {}
        issue_number = int(content.get("number") or 0)
        for finding in audit_item(item):
            if issue_number in exclusions and finding.code in DATE_CODES:
                continue
            findings.append(finding)
    by_code = {}
    for finding in findings:
        by_code[finding.code] = by_code.get(finding.code, 0) + 1
    print(json.dumps({
        "mode": "read_only",
        "items_scanned": len(items),
        "lifecycle_exclusions": sorted(exclusions),
        "findings_count": len(findings),
        "by_code": dict(sorted(by_code.items())),
        "findings": [item.as_dict() for item in findings],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
