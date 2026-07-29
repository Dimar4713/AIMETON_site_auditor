#!/usr/bin/env python3
"""Synchronize GitHub Issue/PR lifecycle with Project V2 status and dates.

Required environment variables:
- GH_TOKEN: token with project and repository issue permissions
- PROJECT_OWNER: user or organization login that owns the project
- PROJECT_NUMBER: Project V2 number

For OPERATION=sync_item these are also required:
- CONTENT_NODE_ID, REPOSITORY, ITEM_NUMBER
- EVENT_NAME, EVENT_ACTION, ITEM_KIND, ITEM_STATE, ITEM_TITLE, ITEM_LABELS

Optional:
- OPERATION: sync_item (default), ensure_schema, or repair_roadmap
- MANUAL_STATUS: explicit target status from workflow_dispatch
- DRY_RUN: report mutations without applying them
- EVENT_AT, ITEM_CLOSED_AT, PR_MERGED_AT, PR_MERGED
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

API = "https://api.github.com"
GRAPHQL = f"{API}/graphql"
STATUSES = {
    "Backlog",
    "Ready",
    "In Progress",
    "In Review",
    "Validation",
    "Blocked",
    "Done",
}
RESUME_PREFIX = "resume:"
STATUS_LABELS = {
    "status:backlog": "Backlog",
    "status:ready": "Ready",
    "status:in-progress": "In Progress",
    "status:in-review": "In Review",
    "status:validation": "Validation",
    "status:blocked": "Blocked",
}
PLAN_DATE_FIELDS = (
    "Start date",
    "Target date",
    "Planned start",
    "Planned finish",
)
ACTUAL_DATE_FIELDS = (
    "Actual start",
    "Actual finish",
)
DATE_FIELDS = PLAN_DATE_FIELDS + ACTUAL_DATE_FIELDS
PLAN_FIELD_PAIRS = (
    ("Start date", "Planned start"),
    ("Target date", "Planned finish"),
)
SEARCH_RECOVERY_SCHEDULE = {
    80: ("2026-07-29", "2026-10-05"),
    81: ("2026-07-29", "2026-07-30"),
    82: ("2026-07-31", "2026-08-03"),
    83: ("2026-08-04", "2026-08-10"),
    84: ("2026-08-11", "2026-08-17"),
    85: ("2026-08-18", "2026-08-31"),
    86: ("2026-08-25", "2026-09-07"),
    87: ("2026-09-01", "2026-09-07"),
    88: ("2026-09-08", "2026-09-21"),
    89: ("2026-09-15", "2026-09-28"),
    90: ("2026-09-22", "2026-10-05"),
}
ROADMAP_VIEWS = {
    "Executive Roadmap": "",
    "Actual Delivery": "",
    "Active Execution": "-status:Done",
}


@dataclass
class Context:
    token: str
    project_owner: str
    project_number: int
    operation: str = "sync_item"
    dry_run: bool = False
    content_node_id: str = ""
    repository: str = ""
    item_number: int = 0
    event_name: str = ""
    event_action: str = ""
    item_kind: str = "issue"
    item_state: str = "open"
    item_title: str = ""
    labels: set[str] | None = None
    manual_status: str = ""
    event_at: str = ""
    item_closed_at: str = ""
    pr_merged_at: str = ""
    pr_merged: bool = False

    def __post_init__(self) -> None:
        if self.labels is None:
            self.labels = set()


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def parse_bool(value: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"", "0", "false", "no", "off"}:
        return False
    if normalized in {"1", "true", "yes", "on"}:
        return True
    raise RuntimeError(f"Invalid boolean value: {value!r}")


def load_context() -> Context:
    token = env("GH_TOKEN")
    owner = env("PROJECT_OWNER")
    number = env("PROJECT_NUMBER")
    operation = env("OPERATION", "sync_item")
    missing = [
        key
        for key, value in {
            "GH_TOKEN": token,
            "PROJECT_OWNER": owner,
            "PROJECT_NUMBER": number,
        }.items()
        if not value
    ]
    if operation not in {"sync_item", "ensure_schema", "repair_roadmap"}:
        raise RuntimeError(f"Unsupported OPERATION: {operation}")
    if operation == "sync_item":
        for key in ("CONTENT_NODE_ID", "REPOSITORY", "ITEM_NUMBER"):
            if not env(key):
                missing.append(key)
    if missing:
        raise RuntimeError("Missing required variables: " + ", ".join(missing))

    labels = {
        item.strip().lower()
        for item in env("ITEM_LABELS").split(",")
        if item.strip()
    }
    return Context(
        token=token,
        project_owner=owner,
        project_number=int(number),
        operation=operation,
        dry_run=parse_bool(env("DRY_RUN")),
        content_node_id=env("CONTENT_NODE_ID"),
        repository=env("REPOSITORY"),
        item_number=int(env("ITEM_NUMBER") or "0"),
        event_name=env("EVENT_NAME"),
        event_action=env("EVENT_ACTION"),
        item_kind=env("ITEM_KIND", "issue"),
        item_state=env("ITEM_STATE", "open"),
        item_title=env("ITEM_TITLE"),
        labels=labels,
        manual_status=env("MANUAL_STATUS"),
        event_at=env("EVENT_AT"),
        item_closed_at=env("ITEM_CLOSED_AT"),
        pr_merged_at=env("PR_MERGED_AT"),
        pr_merged=parse_bool(env("PR_MERGED")),
    )


def request_json(
    url: str,
    token: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
        raise RuntimeError(
            f"GitHub API {exc.code} for {method} {url}: {detail}"
        ) from exc


def graphql(
    ctx: Context,
    query: str,
    variables: dict[str, Any],
) -> dict[str, Any]:
    result = request_json(
        GRAPHQL,
        ctx.token,
        method="POST",
        payload={"query": query, "variables": variables},
    )
    if result.get("errors"):
        raise RuntimeError(
            "GitHub GraphQL error: "
            + json.dumps(result["errors"], ensure_ascii=False)
        )
    return result["data"]


PROJECT_FIELDS = """
  id
  title
  fields(first:100) { nodes {
    ... on ProjectV2Field { id name dataType }
    ... on ProjectV2SingleSelectField {
      id
      name
      dataType
      options { id name }
    }
  } }
  views(first:100) { nodes { id name layout filter } }
"""


def get_project(ctx: Context) -> dict[str, Any]:
    user_query = f"""
    query($login:String!, $number:Int!) {{
      user(login:$login) {{ projectV2(number:$number) {{ {PROJECT_FIELDS} }} }}
    }}
    """
    data = graphql(
        ctx,
        user_query,
        {"login": ctx.project_owner, "number": ctx.project_number},
    )
    project = (data.get("user") or {}).get("projectV2")
    if project:
        return project

    org_query = f"""
    query($login:String!, $number:Int!) {{
      organization(login:$login) {{
        projectV2(number:$number) {{ {PROJECT_FIELDS} }}
      }}
    }}
    """
    data = graphql(
        ctx,
        org_query,
        {"login": ctx.project_owner, "number": ctx.project_number},
    )
    project = (data.get("organization") or {}).get("projectV2")
    if not project:
        raise RuntimeError(
            f"Project V2 #{ctx.project_number} not found for {ctx.project_owner}"
        )
    return project


def _create_date_field(
    ctx: Context,
    project: dict[str, Any],
    name: str,
) -> dict[str, Any]:
    if ctx.dry_run:
        return {"id": f"dry-run:{name}", "name": name, "dataType": "DATE"}
    mutation = """
    mutation($project:ID!, $name:String!) {
      createProjectV2Field(input:{
        projectId:$project, dataType:DATE, name:$name
      }) {
        projectV2Field {
          ... on ProjectV2Field { id name dataType }
        }
      }
    }
    """
    data = graphql(
        ctx,
        mutation,
        {"project": project["id"], "name": name},
    )
    return data["createProjectV2Field"]["projectV2Field"]


def _create_roadmap_view(
    ctx: Context,
    project: dict[str, Any],
    name: str,
    filter_query: str,
) -> dict[str, Any]:
    if ctx.dry_run:
        return {
            "id": f"dry-run:{name}",
            "name": name,
            "layout": "ROADMAP_LAYOUT",
            "filter": filter_query,
        }
    mutation = """
    mutation($project:ID!, $name:String!) {
      createProjectV2View(input:{
        projectId:$project, name:$name, layout:ROADMAP_LAYOUT
      }) {
        projectV2View { id name layout filter }
      }
    }
    """
    data = graphql(
        ctx,
        mutation,
        {"project": project["id"], "name": name},
    )
    view = data["createProjectV2View"]["projectV2View"]
    if filter_query:
        update = """
        mutation($view:ID!, $filter:String!) {
          updateProjectV2View(input:{viewId:$view, filter:$filter}) {
            projectV2View { id name layout filter }
          }
        }
        """
        data = graphql(
            ctx,
            update,
            {"view": view["id"], "filter": filter_query},
        )
        view = data["updateProjectV2View"]["projectV2View"]
    return view


def ensure_project_schema(
    ctx: Context,
    project: dict[str, Any],
) -> dict[str, list[str]]:
    fields = [item for item in project["fields"]["nodes"] if item]
    fields_by_name = {item["name"]: item for item in fields}
    for name in DATE_FIELDS:
        existing = fields_by_name.get(name)
        if existing and existing.get("dataType") != "DATE":
            raise RuntimeError(
                f"Project field {name!r} exists with type "
                f"{existing.get('dataType')!r}, expected DATE"
            )

    views = [item for item in project["views"]["nodes"] if item]
    views_by_name = {item["name"]: item for item in views}
    for name in ROADMAP_VIEWS:
        existing = views_by_name.get(name)
        if existing and existing.get("layout") != "ROADMAP_LAYOUT":
            raise RuntimeError(
                f"Project view {name!r} exists with layout "
                f"{existing.get('layout')!r}, expected ROADMAP_LAYOUT"
            )

    created_fields: list[str] = []
    for name in DATE_FIELDS:
        existing = fields_by_name.get(name)
        if existing:
            continue
        created = _create_date_field(ctx, project, name)
        project["fields"]["nodes"].append(created)
        fields_by_name[name] = created
        created_fields.append(name)

    created_views: list[str] = []
    for name, filter_query in ROADMAP_VIEWS.items():
        existing = views_by_name.get(name)
        if existing:
            continue
        created = _create_roadmap_view(ctx, project, name, filter_query)
        project["views"]["nodes"].append(created)
        views_by_name[name] = created
        created_views.append(name)

    return {
        "created_fields": created_fields,
        "created_views": created_views,
    }


def find_or_add_item(
    ctx: Context,
    project_id: str,
) -> tuple[str, str | None, dict[str, str]]:
    cursor: str | None = None
    while True:
        query = """
        query($project:ID!, $cursor:String) {
          node(id:$project) { ... on ProjectV2 {
            items(first:100, after:$cursor) {
              nodes {
                id
                content {
                  ... on Issue { id }
                  ... on PullRequest { id }
                }
                fieldValues(first:50) { nodes {
                  ... on ProjectV2ItemFieldSingleSelectValue {
                    name
                    field {
                      ... on ProjectV2SingleSelectField { name }
                    }
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
        data = graphql(
            ctx,
            query,
            {"project": project_id, "cursor": cursor},
        )
        items = data["node"]["items"]
        for item in items["nodes"]:
            content = item.get("content") or {}
            if content.get("id") != ctx.content_node_id:
                continue
            current_status = None
            dates: dict[str, str] = {}
            for value in item["fieldValues"]["nodes"]:
                field = value.get("field") or {}
                name = field.get("name")
                if name == "Status":
                    current_status = value.get("name")
                elif name in DATE_FIELDS and value.get("date"):
                    dates[name] = value["date"]
            return item["id"], current_status, dates
        if not items["pageInfo"]["hasNextPage"]:
            break
        cursor = items["pageInfo"]["endCursor"]

    if ctx.dry_run:
        return "dry-run:item", None, {}
    mutation = """
    mutation($project:ID!, $content:ID!) {
      addProjectV2ItemById(input:{
        projectId:$project, contentId:$content
      }) { item { id } }
    }
    """
    data = graphql(
        ctx,
        mutation,
        {"project": project_id, "content": ctx.content_node_id},
    )
    return data["addProjectV2ItemById"]["item"]["id"], None, {}


def list_project_items(
    ctx: Context,
    project_id: str,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        query = """
        query($project:ID!, $cursor:String) {
          node(id:$project) { ... on ProjectV2 {
            items(first:100, after:$cursor) {
              nodes {
                id
                content {
                  ... on Issue {
                    id number title body
                    repository { nameWithOwner }
                  }
                  ... on PullRequest {
                    id number title body
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
        data = graphql(
            ctx,
            query,
            {"project": project_id, "cursor": cursor},
        )
        items = data["node"]["items"]
        result.extend(items["nodes"])
        if not items["pageInfo"]["hasNextPage"]:
            return result
        cursor = items["pageInfo"]["endCursor"]


def _item_dates(item: dict[str, Any]) -> dict[str, str]:
    dates: dict[str, str] = {}
    for value in item.get("fieldValues", {}).get("nodes", []):
        field = value.get("field") or {}
        name = field.get("name")
        date = value.get("date")
        if name in DATE_FIELDS and date:
            dates[name] = date
    return dates


def _declared_plan_dates(
    content: dict[str, Any],
    repository: str,
) -> tuple[str, str] | None:
    content_repository = (content.get("repository") or {}).get(
        "nameWithOwner"
    )
    if content_repository != repository:
        return None
    number = content.get("number")
    if number in SEARCH_RECOVERY_SCHEDULE:
        return SEARCH_RECOVERY_SCHEDULE[number]

    body = content.get("body") or ""
    start = re.search(
        r"Planned start:\s*\*\*(\d{4}-\d{2}-\d{2})\*\*",
        body,
    )
    finish = re.search(
        r"Planned finish:\s*\*\*(\d{4}-\d{2}-\d{2})\*\*",
        body,
    )
    if bool(start) != bool(finish):
        raise RuntimeError(
            f"Item #{number} declares only one planned date"
        )
    if not start:
        return None
    return start.group(1), finish.group(1)


def plan_roadmap_repairs(
    ctx: Context,
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    repairs: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for item in items:
        content = item.get("content") or {}
        dates = _item_dates(item)
        declared = _declared_plan_dates(content, ctx.repository)
        declared_by_pair = (
            {
                "Start date": declared[0],
                "Target date": declared[1],
            }
            if declared
            else {}
        )
        updates: dict[str, str] = {}
        for canonical, mirror in PLAN_FIELD_PAIRS:
            values = {
                dates[name]
                for name in (canonical, mirror)
                if dates.get(name)
            }
            declared_value = declared_by_pair.get(canonical)
            if declared_value:
                values.add(declared_value)
            if len(values) > 1:
                conflicts.append(
                    {
                        "item": content.get("number"),
                        "title": content.get("title"),
                        "field_pair": [canonical, mirror],
                        "values": sorted(values),
                    }
                )
                continue
            if not values:
                continue
            desired = next(iter(values))
            if not dates.get(canonical):
                updates[canonical] = desired
            if not dates.get(mirror):
                updates[mirror] = desired
        if updates:
            repairs.append(
                {
                    "item_id": item["id"],
                    "number": content.get("number"),
                    "title": content.get("title"),
                    "updates": updates,
                }
            )
    return repairs, conflicts


def repair_roadmap_dates(
    ctx: Context,
    project: dict[str, Any],
) -> dict[str, Any]:
    items = list_project_items(ctx, project["id"])
    repairs, conflicts = plan_roadmap_repairs(ctx, items)
    if conflicts:
        raise RuntimeError(
            "Roadmap date conflicts detected; no dates were written: "
            + json.dumps(conflicts, ensure_ascii=False)
        )
    for repair in repairs:
        update_date_fields(
            ctx,
            project,
            repair["item_id"],
            repair["updates"],
        )

    coverage = {
        name: sum(1 for item in items if _item_dates(item).get(name))
        for name in PLAN_DATE_FIELDS
    }
    return {
        "items_scanned": len(items),
        "items_repaired": len(repairs),
        "field_updates": sum(
            len(repair["updates"]) for repair in repairs
        ),
        "repairs": repairs,
        "coverage_before": coverage,
    }


def ensure_label(
    ctx: Context,
    name: str,
    color: str = "D4C5F9",
) -> None:
    if ctx.dry_run:
        return
    owner, repo = ctx.repository.split("/", 1)
    try:
        request_json(
            f"{API}/repos/{owner}/{repo}/labels",
            ctx.token,
            method="POST",
            payload={
                "name": name,
                "color": color,
                "description": "AIMETON workflow lifecycle label",
            },
        )
    except RuntimeError as exc:
        if "already_exists" not in str(exc) and "422" not in str(exc):
            raise


def add_label(ctx: Context, name: str) -> None:
    if ctx.dry_run:
        return
    ensure_label(ctx, name)
    owner, repo = ctx.repository.split("/", 1)
    request_json(
        f"{API}/repos/{owner}/{repo}/issues/{ctx.item_number}/labels",
        ctx.token,
        method="POST",
        payload={"labels": [name]},
    )


def remove_label(ctx: Context, name: str) -> None:
    if ctx.dry_run:
        return
    owner, repo = ctx.repository.split("/", 1)
    encoded = urllib.parse.quote(name, safe="")
    try:
        request_json(
            f"{API}/repos/{owner}/{repo}/issues/"
            f"{ctx.item_number}/labels/{encoded}",
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
            candidate = (
                label[len(RESUME_PREFIX):]
                .replace("-", " ")
                .title()
            )
            if candidate in STATUSES - {"Blocked", "Done"}:
                return candidate
    return None


def choose_status(ctx: Context, current: str | None) -> str:
    if ctx.manual_status:
        if ctx.manual_status not in STATUSES:
            raise RuntimeError(
                f"Unsupported MANUAL_STATUS: {ctx.manual_status}"
            )
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
        if ctx.event_action in {
            "opened",
            "ready_for_review",
            "reopened",
            "review_requested",
        }:
            return "In Review"
    if ctx.event_action == "reopened":
        return "In Progress"
    if ctx.event_action == "opened":
        return "Backlog"
    return current or "Backlog"


def _date_from_timestamp(value: str, label: str) -> str:
    if not value:
        raise RuntimeError(f"Missing timestamp for {label}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError(
            f"Invalid ISO timestamp for {label}: {value!r}"
        ) from exc
    return parsed.date().isoformat()


def determine_actual_date_updates(
    ctx: Context,
    current_status: str | None,
    target_status: str,
    current_dates: dict[str, str],
) -> dict[str, str]:
    updates: dict[str, str] = {}
    if (
        target_status == "In Progress"
        and current_status != "In Progress"
        and "Actual start" not in current_dates
    ):
        timestamp = ctx.event_at or datetime.now(UTC).isoformat()
        updates["Actual start"] = _date_from_timestamp(
            timestamp,
            "Actual start",
        )

    finish_timestamp = ""
    if (
        ctx.item_kind == "issue"
        and ctx.event_action == "closed"
        and ctx.item_state == "closed"
    ):
        finish_timestamp = ctx.item_closed_at
    elif (
        ctx.item_kind == "pull_request"
        and ctx.event_action == "closed"
        and ctx.pr_merged
    ):
        finish_timestamp = ctx.pr_merged_at

    if finish_timestamp and "Actual finish" not in current_dates:
        updates["Actual finish"] = _date_from_timestamp(
            finish_timestamp,
            "Actual finish",
        )

    start = updates.get("Actual start") or current_dates.get("Actual start")
    finish = (
        updates.get("Actual finish")
        or current_dates.get("Actual finish")
    )
    if start and finish and finish < start:
        raise RuntimeError(
            f"Actual finish {finish} is earlier than Actual start {start}"
        )
    return updates


def update_status(
    ctx: Context,
    project: dict[str, Any],
    item_id: str,
    target: str,
) -> None:
    status_field = next(
        (
            field
            for field in project["fields"]["nodes"]
            if field and field.get("name") == "Status"
        ),
        None,
    )
    if not status_field:
        raise RuntimeError(
            "Project has no single-select field named Status"
        )
    option = next(
        (
            item
            for item in status_field["options"]
            if item["name"].casefold() == target.casefold()
        ),
        None,
    )
    if not option:
        available = ", ".join(
            item["name"] for item in status_field["options"]
        )
        raise RuntimeError(
            f"Status option {target!r} not found. Available: {available}"
        )
    if ctx.dry_run:
        return
    mutation = """
    mutation($project:ID!, $item:ID!, $field:ID!, $option:String!) {
      updateProjectV2ItemFieldValue(input:{
        projectId:$project,
        itemId:$item,
        fieldId:$field,
        value:{singleSelectOptionId:$option}
      }) { projectV2Item { id } }
    }
    """
    graphql(
        ctx,
        mutation,
        {
            "project": project["id"],
            "item": item_id,
            "field": status_field["id"],
            "option": option["id"],
        },
    )


def update_date_fields(
    ctx: Context,
    project: dict[str, Any],
    item_id: str,
    updates: dict[str, str],
) -> None:
    fields_by_name = {
        field["name"]: field
        for field in project["fields"]["nodes"]
        if field and field.get("name") in DATE_FIELDS
    }
    mutation = """
    mutation(
      $project:ID!,
      $item:ID!,
      $field:ID!,
      $date:Date!
    ) {
      updateProjectV2ItemFieldValue(input:{
        projectId:$project,
        itemId:$item,
        fieldId:$field,
        value:{date:$date}
      }) { projectV2Item { id } }
    }
    """
    for name, date_value in updates.items():
        field = fields_by_name.get(name)
        if not field:
            raise RuntimeError(f"Project has no date field named {name}")
        if ctx.dry_run:
            continue
        graphql(
            ctx,
            mutation,
            {
                "project": project["id"],
                "item": item_id,
                "field": field["id"],
                "date": date_value,
            },
        )


def main() -> int:
    ctx = load_context()
    project = get_project(ctx)
    schema_changes = ensure_project_schema(ctx, project)
    if ctx.operation == "ensure_schema":
        print(
            json.dumps(
                {
                    "project": project["title"],
                    "operation": ctx.operation,
                    "dry_run": ctx.dry_run,
                    **schema_changes,
                    "roadmap_date_mapping": "one-time-ui-configuration",
                },
                ensure_ascii=False,
            )
        )
        return 0
    if ctx.operation == "repair_roadmap":
        result = repair_roadmap_dates(ctx, project)
        print(
            json.dumps(
                {
                    "project": project["title"],
                    "operation": ctx.operation,
                    "dry_run": ctx.dry_run,
                    **schema_changes,
                    **result,
                },
                ensure_ascii=False,
            )
        )
        return 0

    item_id, current, current_dates = find_or_add_item(
        ctx,
        project["id"],
    )
    target = choose_status(ctx, current)
    date_updates = determine_actual_date_updates(
        ctx,
        current,
        target,
        current_dates,
    )
    update_date_fields(ctx, project, item_id, date_updates)

    if target == "Blocked" and current not in {None, "Blocked", "Done"}:
        for label in list(ctx.labels):
            if label.startswith(RESUME_PREFIX):
                remove_label(ctx, label)
        add_label(ctx, f"{RESUME_PREFIX}{slug(current)}")
    elif current == "Blocked" and target != "Blocked":
        for label in list(ctx.labels):
            if label.startswith(RESUME_PREFIX):
                remove_label(ctx, label)

    update_status(ctx, project, item_id, target)
    print(
        json.dumps(
            {
                "project": project["title"],
                "item": ctx.item_number,
                "from": current,
                "to": target,
                "date_updates": date_updates,
                "dry_run": ctx.dry_run,
                **schema_changes,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"Project status sync failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
