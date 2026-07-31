#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any

GRAPHQL = "https://api.github.com/graphql"
DATE_FIELDS = {"Actual start", "Actual finish"}


@dataclass(frozen=True)
class Proposal:
    repository: str
    number: int
    kind: str
    title: str
    item_id: str
    updates: dict[str, str]
    evidence: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "number": self.number,
            "kind": self.kind,
            "title": self.title,
            "item_id": self.item_id,
            "updates": self.updates,
            "evidence": self.evidence,
        }


def date_only(value: str | None) -> str | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()


def request_graphql(token: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps({"query": query, "variables": variables}).encode()
    request = urllib.request.Request(
        GRAPHQL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "aimeton-project-actual-dates-backfill",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read().decode())
    if result.get("errors"):
        raise RuntimeError(json.dumps(result["errors"], ensure_ascii=False))
    return result["data"]


def project_id(token: str, owner: str, number: int) -> str:
    user_query = """
    query($login:String!, $number:Int!) {
      user(login:$login) { projectV2(number:$number) { id } }
    }
    """
    data = request_graphql(token, user_query, {"login": owner, "number": number})
    project = (data.get("user") or {}).get("projectV2")
    if project:
        return project["id"]
    org_query = """
    query($login:String!, $number:Int!) {
      organization(login:$login) { projectV2(number:$number) { id } }
    }
    """
    data = request_graphql(token, org_query, {"login": owner, "number": number})
    project = (data.get("organization") or {}).get("projectV2")
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
              ... on Issue {
                number title state createdAt closedAt
                repository { nameWithOwner }
                timelineItems(first:100, itemTypes:[CROSS_REFERENCED_EVENT]) {
                  nodes {
                    ... on CrossReferencedEvent {
                      source {
                        __typename
                        ... on PullRequest { createdAt repository { nameWithOwner } }
                      }
                    }
                  }
                }
              }
              ... on PullRequest {
                number title state createdAt mergedAt
                repository { nameWithOwner }
              }
            }
            fieldValues(first:100) { nodes {
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


def current_dates(item: dict[str, Any]) -> dict[str, str]:
    dates: dict[str, str] = {}
    for value in (item.get("fieldValues") or {}).get("nodes", []):
        field = value.get("field") or {}
        name = field.get("name")
        if name in DATE_FIELDS and value.get("date"):
            dates[name] = value["date"]
    return dates


def earliest_issue_execution(content: dict[str, Any]) -> tuple[str | None, str | None]:
    repo = (content.get("repository") or {}).get("nameWithOwner")
    candidates: list[str] = []
    for node in ((content.get("timelineItems") or {}).get("nodes") or []):
        source = (node or {}).get("source") or {}
        source_repo = (source.get("repository") or {}).get("nameWithOwner")
        if source.get("__typename") == "PullRequest" and source_repo == repo and source.get("createdAt"):
            candidates.append(source["createdAt"])
    if not candidates:
        return None, None
    selected = min(candidates)
    return date_only(selected), selected


def plan_item(item: dict[str, Any]) -> tuple[Proposal | None, dict[str, Any] | None]:
    content = item.get("content") or {}
    if not content:
        return None, None
    kind = content.get("__typename") or "Unknown"
    repo = (content.get("repository") or {}).get("nameWithOwner", "")
    number = int(content.get("number") or 0)
    title = content.get("title") or ""
    existing = current_dates(item)
    updates: dict[str, str] = {}
    evidence: dict[str, str] = {}

    if kind == "PullRequest":
        start = date_only(content.get("createdAt"))
        finish = date_only(content.get("mergedAt"))
        if start and "Actual start" not in existing:
            updates["Actual start"] = start
            evidence["Actual start"] = f"pull_request.createdAt={content['createdAt']}"
        if finish and "Actual finish" not in existing:
            updates["Actual finish"] = finish
            evidence["Actual finish"] = f"pull_request.mergedAt={content['mergedAt']}"
    elif kind == "Issue":
        start, start_raw = earliest_issue_execution(content)
        finish = date_only(content.get("closedAt"))
        if start and "Actual start" not in existing:
            updates["Actual start"] = start
            evidence["Actual start"] = f"earliest_cross_referenced_pr.createdAt={start_raw}"
        if finish and "Actual finish" not in existing:
            updates["Actual finish"] = finish
            evidence["Actual finish"] = f"issue.closedAt={content['closedAt']}"

    effective_start = existing.get("Actual start") or updates.get("Actual start")
    effective_finish = existing.get("Actual finish") or updates.get("Actual finish")
    if effective_finish and not effective_start:
        return None, {
            "code": "finish_without_provable_start",
            "repository": repo,
            "number": number,
            "kind": kind,
            "title": title,
            "finish": effective_finish,
        }
    if effective_start and effective_finish and effective_finish < effective_start:
        return None, {
            "code": "finish_before_start",
            "repository": repo,
            "number": number,
            "kind": kind,
            "title": title,
            "start": effective_start,
            "finish": effective_finish,
        }
    if not updates:
        return None, None
    return Proposal(repo, number, kind, title, item["id"], updates, evidence), None


def build_plan(items: list[dict[str, Any]]) -> dict[str, Any]:
    proposals: list[Proposal] = []
    unresolved: list[dict[str, Any]] = []
    for item in items:
        proposal, conflict = plan_item(item)
        if proposal:
            proposals.append(proposal)
        if conflict:
            unresolved.append(conflict)
    proposals.sort(key=lambda item: (item.repository, item.kind, item.number))
    unresolved.sort(key=lambda item: (item["repository"], item["kind"], item["number"]))
    return {
        "mode": "dry_run",
        "project_mutations": 0,
        "items_scanned": len(items),
        "items_with_proposals": len(proposals),
        "field_updates": sum(len(item.updates) for item in proposals),
        "unresolved_count": len(unresolved),
        "apply_allowed": not unresolved,
        "proposals": [item.as_dict() for item in proposals],
        "unresolved": unresolved,
    }


def main() -> None:
    token = os.environ["GH_TOKEN"]
    owner = os.environ["PROJECT_OWNER"]
    number = int(os.environ["PROJECT_NUMBER"])
    items = load_items(token, project_id(token, owner, number))
    print(json.dumps(build_plan(items), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
