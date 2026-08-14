#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from app.search_gap_shadow_action_inventory import summarize_shadow_actions
from app.search_gap_trace_match_inventory import build_shadow_query_match_summary
from app.search_provider_attribution import build_latest_hunter_provider_attribution
from app.trace_ledger import SQLiteTraceLedger, TraceEvent


def read_inventory_events_readonly(trace_db: Path) -> list[TraceEvent]:
    uri = f"{trace_db.expanduser().resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5.0) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only = ON")
        rows = db.execute(
            """
            SELECT * FROM mission_trace_events
            WHERE
                (
                    component = 'search_refinement_shadow'
                    AND operation IN ('follow_up_query_suggested', 'refinement_observed')
                )
                OR
                (
                    component = 'search_gateway'
                    AND operation IN ('query_planned', 'response_received', 'result_item')
                )
                OR
                (
                    component = 'hunter'
                    AND operation IN ('hunt_plan', 'hunt_search_wave_observed', 'hunt_funnel_complete')
                )
            ORDER BY created_at, mission_id, attempt_id, sequence
            """
        ).fetchall()
    return [SQLiteTraceLedger._row(row) for row in rows]


def build_inventory_report(trace_db: Path) -> dict[str, object]:
    events = read_inventory_events_readonly(trace_db)
    report = build_shadow_query_match_summary(events)
    report["provider_attribution"] = build_latest_hunter_provider_attribution(events)
    report["shadow_action_inventory"] = summarize_shadow_actions(events)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace_db", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = build_inventory_report(args.trace_db)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
