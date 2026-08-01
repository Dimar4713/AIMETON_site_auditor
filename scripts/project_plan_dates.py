#!/usr/bin/env python3
"""Assign and verify planned date windows for AIMETON GitHub Project items."""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

GRAPHQL = "https://api.github.com/graphql"
PLAN_FIELDS = ("Start date", "Target date", "Planned start", "Planned finish")
PLAN_PAIRS = (
    ("Start date", "Planned start"),
    ("Target date", "Planned finish"),
)


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def gql(token: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        GRAPHQL,
        data=json.dumps({"query": query, "variables": variables}).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "aimeton-project-plan-dates",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode())
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"], ensure_ascii=False))
    return payload["data"]


def iso_date(value: str) -> str:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()


def priority_days(title: str, labels: list[str], kind: str) -> int:
    text = " ".join([title, *labels]).upper()
    if "[P0]" in text or "PRIORITY:P0" in text:
        return 1
    if "[P1]" in text or "PRIORITY:P1" in text:
        return 3
    if "[P2]" in text or "PRIORITY:P2" in text:
        return 7
    if "[P3]" in text or "PRIORITY:P3" in text:
        return 14
    return 1 if kind == "PullRequest" else 3


def planned_window(content: dict[str, Any]) -> tuple[str, str]:
    created = iso_date(content["createdAt"])
    closed_at = content.get("closedAt") or content.get("mergedAt")
    if closed_at:
        finish = iso_date(closed_at)
    else:
        start_dt = datetime.fromisoformat(created).replace(tzinfo=timezone.utc)
        finish = (
            start_dt
            + timedelta(
                days=priority_days(
                    content.get("title") or "",
                    [
                        node["name"]
                        for node in (content.get("labels") or {}).get("nodes", [])
                    ],
                    content.get("__typename") or "Issue",
                )
            )
        ).date().isoformat()
    if finish < created:
        raise RuntimeError(f"planned finish {finish} precedes start {created}")
    return created, finish


def get_project(token: str, owner: str, number: int) -> dict[str, Any]:
    fields = """
      id title
      fields(first:100) { nodes {
        ... on ProjectV2Field { id name dataType }
      } }
    """
    for owner_type in ("user", "organization"):
        data = gql(
            token,
            f"""
            query($login:String!, $number:Int!) {{
              {owner_type}(login:$login) {{
                projectV2(number:$number) {{ {fields} }}
              }}
            }}
            """,
            {"login": owner, "number": number},
        )
        project = (data.get(owner_type) or {}).get("projectV2")
        if project:
            return project
    raise RuntimeError(f"Project #{number} not found for {owner}")


def canonical_fields(project: dict[str, Any]) -> dict[str, dict[str, Any]]:
    nodes = [node for node in project["fields"]["nodes"] if node]
    result: dict[str, dict[str, Any]] = {}
    for expected in PLAN_FIELDS:
        matches = [
            node
            for node in nodes
            if node.get("name", "").casefold() == expected.casefold()
        ]
        if len(matches) != 1:
            raise RuntimeError(
                f"expected exactly one field {expected!r}, found {len(matches)}"
            )
        field = matches[0]
        if field.get("name") != expected or field.get("dataType") != "DATE":
            raise RuntimeError(f"non-canonical Project field: {field}")
        result[expected] = field
    return result


def list_items(token: str, project_id: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cursor = None
    while True:
        data = gql(
            token,
            """
            query($project:ID!, $cursor:String) {
              node(id:$project) { ... on ProjectV2 {
                items(first:100, after:$cursor) {
                  nodes {
                    id
                    content {
                      __typename
                      ... on Issue {
                        id number title createdAt closedAt
                        labels(first:20){nodes{name}}
                        repository{nameWithOwner}
                      }
                      ... on PullRequest {
                        id number title createdAt closedAt mergedAt
                        labels(first:20){nodes{name}}
                        repository{nameWithOwner}
                      }
                    }
                    fieldValues(first:100) { nodes {
                      ... on ProjectV2ItemFieldDateValue {
                        date field { ... on ProjectV2Field { id name } }
                      }
                    } }
                  }
                  pageInfo { hasNextPage endCursor }
                }
              } }
            }
            """,
            {"project": project_id, "cursor": cursor},
        )
        page = data["node"]["items"]
        items.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            return items
        cursor = page["pageInfo"]["endCursor"]


def existing_dates(item: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    for node in item.get("fieldValues", {}).get("nodes", []):
        field = node.get("field") or {}
        if field.get("name") in PLAN_FIELDS and node.get("date"):
            values[field["name"]] = node["date"]
    return values


def desired_dates(
    current: dict[str, str], derived_start: str, derived_finish: str
) -> dict[str, str]:
    desired: dict[str, str] = {}
    for pair, derived in zip(PLAN_PAIRS, (derived_start, derived_finish), strict=True):
        existing = {current[name] for name in pair if current.get(name)}
        if len(existing) > 1:
            raise RuntimeError(f"conflicting established plan pair {pair}: {sorted(existing)}")
        value = next(iter(existing), derived)
        for name in pair:
            desired[name] = value
    if desired["Target date"] < desired["Start date"]:
        raise RuntimeError(
            f"planned finish {desired['Target date']} precedes start {desired['Start date']}"
        )
    return desired


def set_date(
    token: str,
    project_id: str,
    item_id: str,
    field_id: str,
    value: str,
) -> None:
    gql(
        token,
        """
        mutation($project:ID!, $item:ID!, $field:ID!, $date:Date!) {
          updateProjectV2ItemFieldValue(input:{
            projectId:$project,itemId:$item,fieldId:$field,value:{date:$date}
          }) { projectV2Item { id } }
        }
        """,
        {"project": project_id, "item": item_id, "field": field_id, "date": value},
    )


def apply_item(
    token: str,
    project: dict[str, Any],
    fields: dict[str, dict[str, Any]],
    item: dict[str, Any],
) -> dict[str, Any] | None:
    content = item.get("content") or {}
    repository = (content.get("repository") or {}).get("nameWithOwner")
    if not content or repository != env("REPOSITORY"):
        return None
    current = existing_dates(item)
    derived_start, derived_finish = planned_window(content)
    desired = desired_dates(current, derived_start, derived_finish)
    updates = {name: value for name, value in desired.items() if not current.get(name)}
    for name, value in updates.items():
        set_date(token, project["id"], item["id"], fields[name]["id"], value)
    return {
        "number": content.get("number"),
        "kind": content.get("__typename"),
        "updates": updates,
        "desired": desired,
    }


def verify(token: str, project_id: str, expected: list[dict[str, Any]]) -> None:
    by_number = {
        (item.get("content") or {}).get("number"): item
        for item in list_items(token, project_id)
    }
    failures = []
    for record in expected:
        actual = existing_dates(by_number.get(record["number"]) or {})
        if any(
            actual.get(name) != value
            for name, value in record["desired"].items()
        ):
            failures.append(
                {
                    "number": record["number"],
                    "expected": record["desired"],
                    "actual": actual,
                }
            )
    if failures:
        raise RuntimeError(
            "planned date read-back failed: "
            + json.dumps(failures, ensure_ascii=False)
        )


def main() -> int:
    token = env("GH_TOKEN")
    owner = env("PROJECT_OWNER")
    number = int(env("PROJECT_NUMBER", "0"))
    if not token or not owner or not number or not env("REPOSITORY"):
        raise RuntimeError(
            "GH_TOKEN, PROJECT_OWNER, PROJECT_NUMBER and REPOSITORY are required"
        )
    project = get_project(token, owner, number)
    fields = canonical_fields(project)
    records = []
    for item in list_items(token, project["id"]):
        record = apply_item(token, project, fields, item)
        if record:
            records.append(record)
    verify(token, project["id"], records)
    print(
        json.dumps(
            {
                "project": project["title"],
                "items_verified": len(records),
                "updates": records,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"Project planned dates failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
