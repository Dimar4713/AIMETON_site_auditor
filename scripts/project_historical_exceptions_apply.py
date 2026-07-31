#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from scripts.project_actual_dates_backfill import project_id, request_graphql

MANIFEST = Path("config/project_historical_exceptions.json")
DATE_FIELDS = {"Actual start", "Actual finish"}
APPROVED_DATE_OVERRIDES = {"7", "31", "34", "126", "130", "131", "132"}
APPROVED_LIFECYCLE_EXCLUSIONS = {"19", "32", "128"}


def load_manifest() -> dict[str, Any]:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if set(data["date_overrides"]) != APPROVED_DATE_OVERRIDES:
        raise RuntimeError(
            "Unexpected date override set: "
            f"{sorted(data['date_overrides'])}"
        )
    if set(data["lifecycle_exclusions"]) != APPROVED_LIFECYCLE_EXCLUSIONS:
        raise RuntimeError(
            "Unexpected lifecycle exclusion set: "
            f"{sorted(data['lifecycle_exclusions'])}"
        )
    return data


def load_project(token: str, project: str) -> tuple[dict[str, str], dict[int, dict[str, Any]]]:
    query = """
    query($project:ID!, $cursor:String) {
      node(id:$project) { ... on ProjectV2 {
        fields(first:100) { nodes { ... on ProjectV2Field { id name } } }
        items(first:100, after:$cursor) {
          nodes {
            id
            content {
              ... on Issue { number repository { nameWithOwner } }
              ... on PullRequest { number repository { nameWithOwner } }
            }
            fieldValues(first:100) { nodes {
              ... on ProjectV2ItemFieldDateValue {
                date field { ... on ProjectV2Field { name } }
              }
            } }
          }
          pageInfo { hasNextPage endCursor }
        }
      } }
    }
    """
    fields: dict[str, str] = {}
    items: dict[int, dict[str, Any]] = {}
    cursor = None
    while True:
        data = request_graphql(token, query, {"project": project, "cursor": cursor})["node"]
        if not fields:
            fields = {n["name"]: n["id"] for n in data["fields"]["nodes"] if n.get("name") in DATE_FIELDS}
        for item in data["items"]["nodes"]:
            content = item.get("content") or {}
            if (content.get("repository") or {}).get("nameWithOwner") != "Dimar4713/AIMETON_site_auditor":
                continue
            number = content.get("number")
            if number:
                current = {}
                for value in (item.get("fieldValues") or {}).get("nodes", []):
                    name = (value.get("field") or {}).get("name")
                    if name in DATE_FIELDS and value.get("date"):
                        current[name] = value["date"]
                items[int(number)] = {"item_id": item["id"], "dates": current}
        page = data["items"]["pageInfo"]
        if not page["hasNextPage"]:
            break
        cursor = page["endCursor"]
    if set(fields) != DATE_FIELDS:
        raise RuntimeError(f"Missing date fields: {DATE_FIELDS - set(fields)}")
    return fields, items


def set_date(token: str, project: str, item: str, field: str, value: str) -> None:
    mutation = """
    mutation($project:ID!, $item:ID!, $field:ID!, $date:Date!) {
      updateProjectV2ItemFieldValue(input:{projectId:$project,itemId:$item,fieldId:$field,value:{date:$date}}) {
        projectV2Item { id }
      }
    }
    """
    request_graphql(token, mutation, {"project": project, "item": item, "field": field, "date": value})


def main() -> None:
    token = os.environ["GH_TOKEN"]
    project = project_id(token, os.environ["PROJECT_OWNER"], int(os.environ["PROJECT_NUMBER"]))
    manifest = load_manifest()
    fields, items = load_project(token, project)
    planned = []
    for number_text, override in manifest["date_overrides"].items():
        number = int(number_text)
        item = items.get(number)
        if not item:
            raise RuntimeError(f"Project item #{number} not found")
        for field_name, key in (("Actual start", "actual_start"), ("Actual finish", "actual_finish")):
            expected = override[key]
            existing = item["dates"].get(field_name)
            if existing and existing != expected:
                raise RuntimeError(f"#{number} {field_name} conflict: {existing} != {expected}")
            if not existing:
                planned.append((number, item["item_id"], field_name, expected))
    if os.environ.get("APPLY") != "true":
        print(json.dumps({"mode":"dry_run","planned":planned,"lifecycle_exclusions":manifest["lifecycle_exclusions"]}, ensure_ascii=False, indent=2))
        return
    for number, item_id, field_name, value in planned:
        set_date(token, project, item_id, fields[field_name], value)
    _, after = load_project(token, project)
    errors = []
    for number_text, override in manifest["date_overrides"].items():
        number = int(number_text)
        for field_name, key in (("Actual start", "actual_start"), ("Actual finish", "actual_finish")):
            if after[number]["dates"].get(field_name) != override[key]:
                errors.append(f"#{number} {field_name}")
    result = {"mode":"apply","mutations":len(planned),"readback_errors":errors,"lifecycle_exclusions":manifest["lifecycle_exclusions"],"success":not errors}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
