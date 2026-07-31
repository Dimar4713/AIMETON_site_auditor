#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from typing import Any

from project_actual_dates_backfill import build_plan, load_items, project_id, request_graphql

EXPECTED_ITEMS = 91
EXPECTED_UPDATES = 134
EXPECTED_UNRESOLVED = {7, 19, 31, 32, 34}
APPROVED_CUTOFF = "2026-07-31T12:32:00Z"
DATE_FIELDS = {"Actual start", "Actual finish"}


def approved_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items:
        content = item.get("content") or {}
        created = content.get("createdAt")
        if not created or created <= APPROVED_CUTOFF:
            result.append(item)
    return result


def preflight(items: list[dict[str, Any]]) -> dict[str, Any]:
    plan = build_plan(approved_items(items))
    unresolved = {int(item["number"]) for item in plan["unresolved"]}
    errors: list[str] = []
    if plan["items_with_proposals"] != EXPECTED_ITEMS:
        errors.append(f"proposal_count={plan['items_with_proposals']} expected={EXPECTED_ITEMS}")
    if plan["field_updates"] != EXPECTED_UPDATES:
        errors.append(f"field_updates={plan['field_updates']} expected={EXPECTED_UPDATES}")
    if unresolved != EXPECTED_UNRESOLVED:
        errors.append(f"unresolved={sorted(unresolved)} expected={sorted(EXPECTED_UNRESOLVED)}")
    proposal_numbers = {int(item["number"]) for item in plan["proposals"]}
    overlap = proposal_numbers & EXPECTED_UNRESOLVED
    if overlap:
        errors.append(f"unresolved_in_proposals={sorted(overlap)}")
    return {"plan": plan, "errors": errors, "apply_allowed": not errors}


def project_fields(token: str, project: str) -> dict[str, str]:
    query = """
    query($project:ID!) {
      node(id:$project) { ... on ProjectV2 {
        fields(first:100) { nodes {
          ... on ProjectV2Field { id name dataType }
        } }
      } }
    }
    """
    data = request_graphql(token, query, {"project": project})
    fields: dict[str, str] = {}
    for node in data["node"]["fields"]["nodes"]:
        if node.get("name") in DATE_FIELDS and node.get("dataType") == "DATE":
            fields[node["name"]] = node["id"]
    missing = DATE_FIELDS - fields.keys()
    if missing:
        raise RuntimeError(f"Missing Project date fields: {sorted(missing)}")
    return fields


def update_date(token: str, project: str, item_id: str, field_id: str, value: str) -> None:
    mutation = """
    mutation($project:ID!, $item:ID!, $field:ID!, $date:Date!) {
      updateProjectV2ItemFieldValue(input:{
        projectId:$project,
        itemId:$item,
        fieldId:$field,
        value:{date:$date}
      }) { projectV2Item { id } }
    }
    """
    request_graphql(token, mutation, {
        "project": project,
        "item": item_id,
        "field": field_id,
        "date": value,
    })


def current_dates(item: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in (item.get("fieldValues") or {}).get("nodes", []):
        name = (value.get("field") or {}).get("name")
        if name in DATE_FIELDS and value.get("date"):
            result[name] = value["date"]
    return result


def main() -> None:
    token = os.environ["GH_TOKEN"]
    owner = os.environ["PROJECT_OWNER"]
    number = int(os.environ["PROJECT_NUMBER"])
    confirm = os.environ.get("CONFIRM_APPLY", "")
    if confirm != "APPLY_91_134":
        raise RuntimeError("CONFIRM_APPLY must equal APPLY_91_134")

    project = project_id(token, owner, number)
    before_items = load_items(token, project)
    gate = preflight(before_items)
    if not gate["apply_allowed"]:
        print(json.dumps({"mode": "blocked", **gate}, ensure_ascii=False, indent=2))
        raise SystemExit(2)

    fields = project_fields(token, project)
    applied: list[dict[str, Any]] = []
    for proposal in gate["plan"]["proposals"]:
        for field_name, date_value in proposal["updates"].items():
            update_date(token, project, proposal["item_id"], fields[field_name], date_value)
            applied.append({
                "repository": proposal["repository"],
                "number": proposal["number"],
                "kind": proposal["kind"],
                "field": field_name,
                "value": date_value,
            })

    after_items = load_items(token, project)
    by_id = {item["id"]: item for item in after_items}
    readback_errors: list[str] = []
    for proposal in gate["plan"]["proposals"]:
        dates = current_dates(by_id[proposal["item_id"]])
        for field_name, expected in proposal["updates"].items():
            if dates.get(field_name) != expected:
                readback_errors.append(
                    f"{proposal['repository']}#{proposal['number']} {field_name}: "
                    f"actual={dates.get(field_name)} expected={expected}"
                )

    repeated = build_plan(approved_items(after_items))
    repeated_proposals = [
        item for item in repeated["proposals"]
        if int(item["number"]) not in EXPECTED_UNRESOLVED
    ]
    success = not readback_errors and not repeated_proposals
    report = {
        "mode": "apply",
        "preflight": {
            "items_with_proposals": EXPECTED_ITEMS,
            "field_updates": EXPECTED_UPDATES,
            "unresolved": sorted(EXPECTED_UNRESOLVED),
        },
        "mutations_attempted": len(applied),
        "readback_errors": readback_errors,
        "repeated_dry_run_delta": len(repeated_proposals),
        "unresolved_untouched": sorted(EXPECTED_UNRESOLVED),
        "success": success,
        "applied": applied,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not success:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
