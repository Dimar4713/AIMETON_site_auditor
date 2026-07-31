#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass

HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
CHECKBOX_RE = re.compile(r"^\s*[-*]\s+\[( |x|X)\]\s+(.+?)\s*$", re.MULTILINE)
ISSUE_REF_RE = re.compile(r"(?i)\b(?:part\s+of|closes?|fixes?|resolves?)\s+#(\d+)\b")
DIRECT_ISSUE_REF_RE = re.compile(r"(?<!\w)#(\d+)\b")


@dataclass(frozen=True)
class Validation:
    ok: bool
    errors: tuple[str, ...]


def section(body: str, name: str) -> str | None:
    matches = list(HEADING_RE.finditer(body or ""))
    target = name.casefold()
    for index, match in enumerate(matches):
        if match.group(1).strip().casefold() != target:
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        return body[start:end].strip()
    return None


def validate_pr_body(body: str) -> Validation:
    errors: list[str] = []
    criteria = section(body, "Acceptance criteria affected")
    if criteria is None:
        errors.append("Missing heading: Acceptance criteria affected")
    elif not criteria.strip():
        errors.append("Acceptance criteria affected section is empty")
    if not ISSUE_REF_RE.search(body or ""):
        errors.append("Missing explicit linked Issue: Part of/Closes/Fixes/Resolves #N")
    return Validation(not errors, tuple(errors))


def open_checkboxes(body: str) -> tuple[str, ...]:
    return tuple(text.strip() for mark, text in CHECKBOX_RE.findall(body or "") if mark == " ")


def validate_issue_closure(body: str) -> Validation:
    pending = open_checkboxes(body)
    if not pending:
        return Validation(True, ())
    transfer = section(body, "Debt transfer")
    if transfer and DIRECT_ISSUE_REF_RE.search(transfer):
        return Validation(True, ())
    return Validation(False, (
        f"Issue has {len(pending)} open checkbox(es) and no Debt transfer section with an explicit Issue reference",
    ))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("pr", "issue"))
    parser.add_argument("--body-file", required=True)
    args = parser.parse_args()
    body = open(args.body_file, encoding="utf-8").read()
    result = validate_pr_body(body) if args.mode == "pr" else validate_issue_closure(body)
    print(json.dumps({"ok": result.ok, "errors": result.errors}, ensure_ascii=False))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
