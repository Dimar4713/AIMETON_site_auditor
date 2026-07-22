#!/usr/bin/env python3
"""Compatibility entrypoint for personal or organization-owned GitHub Projects V2."""
from __future__ import annotations

import project_status_sync as sync


def get_project(ctx: sync.Context):
    fields = """
      id
      title
      fields(first:50) { nodes {
        ... on ProjectV2SingleSelectField { id name options { id name } }
      } }
    """

    user_query = f"""
    query($login:String!, $number:Int!) {{
      user(login:$login) {{ projectV2(number:$number) {{ {fields} }} }}
    }}
    """
    data = sync.graphql(ctx, user_query, {"login": ctx.project_owner, "number": ctx.project_number})
    project = (data.get("user") or {}).get("projectV2")
    if project:
        return project

    org_query = f"""
    query($login:String!, $number:Int!) {{
      organization(login:$login) {{ projectV2(number:$number) {{ {fields} }} }}
    }}
    """
    data = sync.graphql(ctx, org_query, {"login": ctx.project_owner, "number": ctx.project_number})
    project = (data.get("organization") or {}).get("projectV2")
    if not project:
        raise RuntimeError(f"Project V2 #{ctx.project_number} not found for {ctx.project_owner}")
    return project


def update_status_case_insensitive(
    ctx: sync.Context,
    project: dict,
    item_id: str,
    target: str,
) -> None:
    """Resolve Project status options case-insensitively while preserving the real option ID."""
    status_field = next(
        (field for field in project["fields"]["nodes"] if field and field.get("name") == "Status"),
        None,
    )
    if not status_field:
        raise RuntimeError("Project has no single-select field named Status")

    option = next(
        (item for item in status_field["options"] if item["name"].casefold() == target.casefold()),
        None,
    )
    if not option:
        available = ", ".join(item["name"] for item in status_field["options"])
        raise RuntimeError(f"Status option {target!r} not found. Available: {available}")

    mutation = """
    mutation($project:ID!, $item:ID!, $field:ID!, $option:String!) {
      updateProjectV2ItemFieldValue(input:{projectId:$project, itemId:$item, fieldId:$field, value:{singleSelectOptionId:$option}}) { projectV2Item { id } }
    }
    """
    sync.graphql(
        ctx,
        mutation,
        {
            "project": project["id"],
            "item": item_id,
            "field": status_field["id"],
            "option": option["id"],
        },
    )


sync.STATUSES.add("Ready")
sync.STATUS_LABELS["status:ready"] = "Ready"
sync.get_project = get_project
sync.update_status = update_status_case_insensitive

if __name__ == "__main__":
    try:
        raise SystemExit(sync.main())
    except Exception as exc:  # noqa: BLE001
        print(f"Project status sync failed: {exc}", file=sync.sys.stderr)
        raise SystemExit(1)
