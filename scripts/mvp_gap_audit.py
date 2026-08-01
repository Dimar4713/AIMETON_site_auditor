#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import sqlite3
import urllib.request
from pathlib import Path


def route_inventory(root: Path) -> list[tuple[str, str, str]]:
    routes: list[tuple[str, str, str]] = []
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
                    continue
                method = dec.func.attr.upper()
                if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}:
                    continue
                if not dec.args or not isinstance(dec.args[0], ast.Constant) or not isinstance(dec.args[0].value, str):
                    continue
                routes.append((method, dec.args[0].value, str(path.relative_to(root.parent))))
    return sorted(set(routes))


def symbol_inventory(root: Path, wanted: set[str]) -> dict[str, list[str]]:
    found = {name: [] for name in wanted}
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in wanted:
                found[node.name].append(str(path.relative_to(root.parent)))
    return found


def db_schema(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {table: [r[1] for r in con.execute(f"PRAGMA table_info('{table}')")] for table in tables}
    finally:
        con.close()


def status_for_routes(routes: list[tuple[str, str, str]], needles: tuple[str, ...]) -> str:
    paths = [p.lower() for _, p, _ in routes]
    hits = sum(any(n in p for p in paths) for n in needles)
    if hits == len(needles):
        return "implemented"
    if hits:
        return "partial"
    return "absent"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stack-dir", default="/opt/aimeton/auditor-stack")
    parser.add_argument("--stage-url", default="https://stage-auditor.aimeton.ru")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    stack = Path(args.stack_dir)
    app_root = stack / "app-source" / "app"
    static_root = stack / "app-source" / "static"
    db_path = stack / "data" / "runtime-core" / "runtime-core.sqlite3"
    sha = (stack / "app-source-sha.txt").read_text(encoding="utf-8").strip() if (stack / "app-source-sha.txt").exists() else "unavailable"

    health_status = "unavailable"
    try:
        with urllib.request.urlopen(args.stage_url.rstrip("/") + "/api/health", timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
            health_status = str(payload.get("status", "unknown"))
    except Exception:
        health_status = "failed"

    routes = route_inventory(app_root)
    wanted = {"AuthProvider", "UserRepository", "MissionRepository", "AdminPolicy", "EntitlementPolicy"}
    symbols = symbol_inventory(app_root, wanted)
    schema = db_schema(db_path)
    static_files = sorted(str(p.relative_to(static_root)) for p in static_root.rglob("*") if p.is_file()) if static_root.exists() else []

    matrix = {
        "login/logout/session/current-user API": status_for_routes(routes, ("login", "logout", "session")),
        "admin user-management API": status_for_routes(routes, ("admin", "user")),
        "mission list/detail API": status_for_routes(routes, ("mission",)),
        "capability/entitlement manifest": status_for_routes(routes, ("capabil",)),
        "user/admin UI entrypoints": "implemented" if any("admin" in f.lower() or "workspace" in f.lower() for f in static_files) else ("partial" if static_files else "absent"),
        "replaceable domain interfaces": "implemented" if all(symbols[n] for n in wanted) else ("partial" if any(symbols[n] for n in wanted) else "absent"),
        "persistent runtime schema": "implemented" if schema else "absent",
    }

    lines = [
        "## SA-MVP-01A live product gap evidence",
        "",
        f"- deployed SHA: `{sha}`",
        f"- stage health: `{health_status}`",
        "- mode: read-only",
        "",
        "### Gap matrix",
        "",
        "| Capability | Status |",
        "|---|---|",
    ]
    lines.extend(f"| {name} | `{status}` |" for name, status in matrix.items())
    lines += ["", "### Routes", ""]
    lines.extend(f"- `{method} {path}` — `{source}`" for method, path, source in routes) if routes else lines.append("- none detected")
    lines += ["", "### Replaceable interfaces", ""]
    for name in sorted(wanted):
        hits = ", ".join(f"`{p}`" for p in symbols[name]) or "absent"
        lines.append(f"- `{name}`: {hits}")
    lines += ["", "### Persistent schema", ""]
    if schema:
        for table, columns in schema.items():
            lines.append(f"- `{table}`: `{','.join(columns)}`")
    else:
        lines.append("- no readable runtime DB schema")
    lines += ["", "### Static UI inventory", ""]
    lines.extend(f"- `{p}`" for p in static_files[:100]) if static_files else lines.append("- none detected")
    lines += ["", "### Recommended order", "", "1. Complete local auth/session and negative authorization tests.", "2. Add mission ownership persistence and cross-user isolation.", "3. Deliver user workspace over capability manifest.", "4. Deliver admin workspace and audit trail.", "5. Run restart/redeploy and stage acceptance with two users plus one admin."]

    Path(args.output).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
