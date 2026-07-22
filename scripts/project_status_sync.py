#!/usr/bin/env python3
"""Synchronize GitHub Issue/PR lifecycle with a Project V2 Status field.

Required environment variables:
- GH_TOKEN: token with project and repository issue permissions
- PROJECT_OWNER: user or organization login that owns the project
- PROJECT_NUMBER: Project V2 number
- CONTENT_NODE_ID: Issue or Pull Request node id
- REPOSITORY: owner/name
- ITEM_NUMBER: issue or PR number
- EVENT_NAME / EVENT_ACTION / ITEM_KIND / ITEM_STATE / ITEM_TITLE / ITEM_LABELS

Optional:
- MANUAL_STATUS: explicit target status from workflow_dispatch
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

API = "https://api.github.com"
GRAPHQL = f"{API}/graphql"
STATUSES = {"Backlog", "In Progress", "In Review", "Validation", "Blocked", "Done"}
RESUME_PREFIX = "resume:"
STATUS_LABELS = {
    "status:backlog": "Backlog",
    "status:in-progress": "In Progress",
    "status:in-review": "In Review",
    "status:validation": "Validation",
    "status:blocked": "Blocked",
}


@dataclass
class Context:
    token: str
    project_owner: str
    project_number: int
    content_node_id: str
    repository: str
    item_number: int
    event_name: str
    event_action: str
    item_kind: str
    item_state: str
    item_title: str
    labels: set[str]
    manual_status: str


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def load_context() -> Context:
    token = env("GH_TOKEN")
    owner = env("PROJECT_OWNER")
    number = env("PROJECT_NUMBER")
    content_id = env("CONTENT_NODE_ID")
    repository = env("REPOSITORY")
    item_number = env("ITEM_NUMBER")
    missing = [
        key
        for key, value in {
            "GH_TOKEN": token,
            "PROJECT_OWNER": owner,
            "PROJECT_NUMBER": number,
            "CONTENT_NODE_ID": content_id,
            "REPOSITORY": repository,
            "ITEM_NUMBER": item_number,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError("Missing required variables: " + ", ".join(missing))
    labels = {x.strip().lower() for x in env("ITEM_LABELS").split(",") if x.strip()}
    return Context(
        token=token,
        project_owner=owner,
        project_number=int(number),
        content_node_id=content_id,
        repository=repository,
        item_number=int(item_number),
        event_name=env("EVENT_NAME"),
        event_action=env("EVENT_ACTION"),
        item_kind=env("ITEM_KIND", "issue"),
        item_state=env("ITEM_STATE", "open"),
        item_title=env("ITEM_TITLE"),
        labels=labels,
        manual_status=env("MANUAL_STATUS"),
    )


def request_json(url: str, token: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "aimeton-project-status-sync",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {exc.code} for {method} {url}: {detail}") from exc


def graphql(ctx: Context, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    result = request_json(GRAPHQL, ctx.token, method="POST", payload={"query": query, "variables": variables})
    if result.get("errors"):
        raise RuntimeError("GitHub GraphQL error: " + json.dumps(result["errors"], ensure_ascii=False))
    return result["data"]


def get_project(ctx: Context) -> dict[str, Any]:
    query = """
    query($login:String!, $number:Int!) {
      user(login:$login) { projectV2(number:$number) { id title fields(first:50) { nodes {
        ... on ProjectV2SingleSelectField { id name options { id name } }
      } } } }
      organization(login:$login) { projectV2(number:$number) { id title fields(first:50) { nodes {
        ... on ProjectV2SingleSelectField { id name options { id name } }
      } } } }
    }
    """
    data = graphql(ctx, query, {"login": ctx.project_owner, "number": ctx.project_number})
    project = (data.get("user") or {}).get("projectV2") or (data.get("organization") or {}).get("projectV2")
    if not project:
        raise RuntimeError(f"Project V2 #{ctx.project_number} not found for {ctx.project_owner}")
    return project


def find_or_add_item(ctx: Context, project_id: str) -> tuple[str, str | None]:
    cursor: str | None = None
    while True:
        query = """
        query($project:ID!, $cursor:String) {
          node(id:$project) { ... on ProjectV2 { items(first:100, after:$cursor) {
            nodes { id content { ... on Issue { id } ... on PullRequest { id } }
              fieldValues(first:20) { nodes { ... on ProjectV2ItemFieldSingleSelectValue { name field { ... on ProjectV2SingleSelectField { name } } } } }
            }
            pageInfo { hasNextPage endCursor }
          } } }
        }
        """
        data = graphql(ctx, query, {"project": project_id, "cursor": cursor})
        items = data["node"]["items"]
        for item in items["nodes"]:
            content = item.get("content") or {}
            if content.get("id") == ctx.content_node_id:
                current = None
                for value in item["fieldValues"]["nodes"]:
                    field = value.get("field") or {}
                    if field.get("name") == "Status":
                        current = value.get("name")
                return item["id"], current
        if not items["pageInfo"]["hasNextPage"]:
            break
        cursor = items["pageInfo"]["endCursor"]

    mutation = """
    mutation($project:ID!, $content:ID!) {
      addProjectV2ItemById(input:{projectId:$project, contentId:$content}) { item { id } }
    }
    """
    data = graphql(ctx, mutation, {"project": project_id, "content": ctx.content_node_id})
    return data["addProjectV2ItemById"]["item"]["id"], None


def ensure_label(ctx: Context, name: str, color: str = "D4C5F9") -> None:
    owner, repo = ctx.repository.split("/", 1)
    try:
        request_json(
            f"{API}/repos/{owner}/{repo}/labels",
            ctx.token,
            method="POST",
            payload={"name": name, "color": color, "description": "AIMETON workflow lifecycle label"},
        )
    except RuntimeError as exc:
        if "already_exists" not in str(exc) and "422" not in str(exc):
            raise


def add_label(ctx: Context, name: str) -> None:
    ensure_label(ctx, name)
    owner, repo = ctx.repository.split("/", 1)
    request_json(
        f"{API}/repos/{owner}/{repo}/issues/{ctx.item_number}/labels",
        ctx.token,
        method="POST",
        payload={"labels": [name]},
    )


def remove_label(ctx: Context, name: str) -> None:
    owner, repo = ctx.repository.split("/", 1)
    try:
        request_json(
            f"{API}/repos/{owner}/{repo}/issues/{ctx.item_number}/labels/{urllib.parse.quote(name, safe='')}",
            ctx.token,
            method="DELETE",
        )
    except RuntimeError as exc:
        if "404" not in str(exc):
            raise


def slug(status: str) -> str:
    return status.lower().replace(" ", "-")


def resume_from_labels(labels: set[str]) -> str | None:
    for label in labels:
        if label.startswith(RESUME_PREFIX):
            candidate = label[len(RESUME_PREFIX):].replace("-", " ").title()
            if candidate in STATUSES - {"Blocked", "Done"}:
                return candidate
    return None


def choose_status(ctx: Context, current: str | None) -> str:
    if ctx.manual_status:
        if ctx.manual_status not in STATUSES:
            raise RuntimeError(f"Unsupported MANUAL_STATUS: {ctx.manual_status}")
        return ctx.manual_status
    if ctx.item_state == "closed" or ctx.event_action == "closed":
        return "Done"
    if "status:blocked" in ctx.labels or "blocked" in ctx.labels:
        return "Blocked"
    resumed = resume_from_labels(ctx.labels)
    if ctx.event_action == "unlabeled" and current == "Blocked":
        return resumed or "In Progress"
    for label, status in STATUS_LABELS.items():
        if label in ctx.labels:
            return status
    if ctx.item_title.upper().startswith("VALIDATION"):
        return "Validation"
    if ctx.item_kind == "pull_request":
        if ctx.event_action == "converted_to_draft":
            return "In Progress"
        if ctx.event_action in {"opened", "ready_for_review", "reopened", "review_requested"}:
            return "In Review"
    if ctx.event_action == "reopened":
        return "In Progress"
    if ctx.event_action == "opened":
        return "Backlog"
    return current or "Backlog"


def update_status(ctx: Context, project: dict[str, Any], item_id: str, target: str) -> None:
    status_field = next((f for f in project["fields"]["nodes"] if f and f.get("name") == "Status"), None)
    if not status_field:
        raise RuntimeError("Project has no single-select field named Status")
    option = next((o for o in status_field["options"] if o["name"] == target), None)
    if not option:
        available = ", ".join(o["name"] for o in status_field["options"])
        raise RuntimeError(f"Status option {target!r} not found. Available: {available}")
    mutation = """
    mutation($project:ID!, $item:ID!, $field:ID!, $option:String!) {
      updateProjectV2ItemFieldValue(input:{projectId:$project, itemId:$item, fieldId:$field, value:{singleSelectOptionId:$option}}) { projectV2Item { id } }
    }
    """
    graphql(ctx, mutation, {"project": project["id"], "item": item_id, "field": status_field["id"], "option": option["id"]})


def main() -> int:
    ctx = load_context()
    project = get_project(ctx)
    item_id, current = find_or_add_item(ctx, project["id"])
    target = choose_status(ctx, current)

    if target == "Blocked" and current and current not in {"Blocked", "Done"}:
        for label in list(ctx.labels):
            if label.startswith(RESUME_PREFIX):
                remove_label(ctx, label)
        resume_label = f"{RESUME_PREFIX}{slug(current)}"
        add_label(ctx, resume_label)
    elif current == "Blocked" and target != "Blocked":
        for label in list(ctx.labels):
            if label.startswith(RESUME_PREFIX):
                remove_label(ctx, label)

    update_status(ctx, project, item_id, target)
    print(json.dumps({"project": project["title"], "item": ctx.item_number, "from": current, "to": target}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"Project status sync failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
