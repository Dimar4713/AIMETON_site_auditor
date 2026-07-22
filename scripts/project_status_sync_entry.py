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


sync.get_project = get_project

if __name__ == "__main__":
    try:
        raise SystemExit(sync.main())
    except Exception as exc:  # noqa: BLE001
        print(f"Project status sync failed: {exc}", file=sync.sys.stderr)
        raise SystemExit(1)
