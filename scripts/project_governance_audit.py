#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass
from typing import Any

GRAPHQL = "https://api.github.com/graphql"
EXECUTION_STATUSES = {"In Progress", "In Review", "Validation"}
TERMINAL_STATUSES = {"Done"}
DATE_FIELDS = {"Actual start", "Actual finish"}


@dataclass(frozen=True)
class AuditFinding:
    code: str
    repository: str
    number: int
    kind: str
    title: str
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "repository": self.repository,
            "number": self.number,
            "kind": self.kind,
            "title": self.title,
            "detail": self.detail,
        }


def checkbox_counts(body: str) -> tuple[int, int]:
    open_count = len(re.findall(r"(?mi)^\s*- \[ \] ", body or ""))
    checked_count = len(re.findall(r"(?mi)^\s*- \[[xX]\] ", body or ""))
    return open_count, checked_count


def audit_item(item: dict[str, Any]) -> list[AuditFinding]:
    content = item.get("content") or {}
    repository = (content.get("repository") or {}).get("nameWithOwner", "")
    number = int(content.get("number") or 0)
    title = content.get("title") or ""
    kind = content.get("__typename") or "Unknown"
    state = (content.get("state") or "").upper()
    merged = bool(content.get("merged"))
    body = content.get("body") or ""

    status = None
    dates: dict[str, str] = {}
    for value in (item.get("fieldValues") or {}).get("nodes", []):
        field = value.get("field") or {}
        name = field.get("name")
        if name == "Status":
            status = value.get("name")
        elif name in DATE_FIELDS and value.get("date"):
            dates[name] = value["date"]

    findings: list[AuditFinding] = []
    if status in EXECUTION_STATUSES and "Actual start" not in dates:
        findings.append(AuditFinding(
            "active_without_actual_start", repository, number, kind, title,
            f"status={status}",
        ))
    completed = state == "CLOSED" or merged or status in TERMINAL_STATUSES
    if completed and "Actual finish" not in dates:
        findings.append(AuditFinding(
            "completed_without_actual_finish", repository, number, kind, title,
            f"state={state}; merged={merged}; status={status}",
        ))
    if "Actual finish" in dates and "Actual start" not in dates:
        findings.append(AuditFinding(
            "actual_finish_without_start", repository, number, kind, title,
            f"actual_finish={dates['Actual finish']}",
        ))
    if dates.get("Actual start") and dates.get("Actual finish") and dates["Actual finish"] < dates["Actual start"]:
        findings.append(AuditFinding(
            "actual_finish_before_start", repository, number, kind, title,
            f"start={dates['Actual start']}; finish={dates['Actual finish']}",
        ))

    open_checks, checked_checks = checkbox_counts(body)
    if completed and open_checks:
        findings.append(AuditFinding(
            "completed_with_open_checkboxes", repository, number, kind, title,
            f"open={open_checks}; checked={checked_checks}",
        ))
    if checked_checks and "Evidence of Done" not in body:
        findings.append(AuditFinding(
            "checked_without_evidence_section", repository, number, kind, title,
            f"checked={checked_checks}",
        ))
    return findings


def request_graphql(token: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps({"query": query, "variables": variables}).encode()
    request = urllib.request.Request(
        GRAPHQL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "aimeton-project-governance-audit",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read().decode())
    if result.get("errors"):
        raise RuntimeError(json.dumps(result["errors"], ensure_ascii=False))
    return result["data"]


def project_id(token: str, owner: str, number: int) -> str:
    query = """
    query($login:String!, $number:Int!) {
      user(login:$login) { projectV2(number:$number) { id } }
      organization(login:$login) { projectV2(number:$number) { id } }
    }
    """
    data = request_graphql(token, query, {"login": owner, "number": number})
    project = (data.get("user") or {}).get("projectV2") or (data.get("organization") or {}).get("projectV2")
    if not project:
        raise RuntimeError("Project not found")
    return project["id"]


def load_items(token: str, project: str) -> list[dict[str, Any]]:
    query = """
    query($project:ID!, $cursor:String) {
      node(id:$project) { ... on ProjectV2 {
        items(first:100, after:$cursor) {
          nodes {
            id
            content {
              __typename
              ... on Issue { number title body state repository { nameWithOwner } }
              ... on PullRequest { number title body state merged repository { nameWithOwner } }
            }
            fieldValues(first:100) { nodes {
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                field { ... on ProjectV2SingleSelectField { name } }
              }
              ... on ProjectV2ItemFieldDateValue {
                date
                field { ... on ProjectV2Field { name } }
              }
            } }
          }
          pageInfo { hasNextPage endCursor }
        }
      } }
    }
    """
    result: list[dict[str, Any]] = []
    cursor = None
    while True:
        data = request_graphql(token, query, {"project": project, "cursor": cursor})
        page = data["node"]["items"]
        result.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            return result
        cursor = page["pageInfo"]["endCursor"]


def main() -> None:
    token = os.environ["GH_TOKEN"]
    owner = os.environ["PROJECT_OWNER"]
    number = int(os.environ["PROJECT_NUMBER"])
    items = load_items(token, project_id(token, owner, number))
    findings = [finding for item in items for finding in audit_item(item)]
    by_code: dict[str, int] = {}
    for finding in findings:
        by_code[finding.code] = by_code.get(finding.code, 0) + 1
    print(json.dumps({
        "mode": "read_only",
        "items_scanned": len(items),
        "findings_count": len(findings),
        "by_code": dict(sorted(by_code.items())),
        "findings": [item.as_dict() for item in findings],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
