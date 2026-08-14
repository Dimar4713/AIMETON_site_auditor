#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import get_args

from app.search_gap_retained_evidence import build_gap_hindsight_report
from app.search_gap_shadow_refinement import GapCode
from app.search_gap_trace_replay import replay_case_from_trace
from app.search_regime_utility import SearchRegime
from app.trace_ledger import SQLiteTraceLedger, TraceEvent


def read_attempt_readonly(
    trace_db: Path,
    mission_id: str,
    attempt_id: str,
) -> list[TraceEvent]:
    """Read an existing trace attempt without migration, WAL changes, or writes."""
    uri = f"{trace_db.expanduser().resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5.0) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only = ON")
        rows = db.execute(
            "SELECT * FROM mission_trace_events "
            "WHERE mission_id = ? AND attempt_id = ? ORDER BY sequence",
            (mission_id, attempt_id),
        ).fetchall()
    return [SQLiteTraceLedger._row(row) for row in rows]


def build_trace_replay_report(
    trace_db: Path,
    *,
    mission_id: str,
    attempt_id: str,
    gap_code: GapCode,
    effective_regime: SearchRegime,
    suggested_follow_up_query: str,
    baseline_domains: list[str] | None = None,
) -> dict[str, object]:
    events = read_attempt_readonly(trace_db, mission_id, attempt_id)
    case = replay_case_from_trace(
        events,
        gap_code=gap_code,
        effective_regime=effective_regime,
        suggested_follow_up_query=suggested_follow_up_query,
        baseline_domains=baseline_domains or [],
    )
    if case is None:
        return {
            "evidence_kind": "search_gap_trace_replay",
            "mission_id": mission_id,
            "attempt_id": attempt_id,
            "case_found": False,
            "record_count": 0,
            "routing_changed": False,
            "steering_enabled": False,
            "promotion_activated": False,
        }

    retained = case.to_retained_outcome()
    report = build_gap_hindsight_report([retained])
    report.update(
        {
            "evidence_kind": "search_gap_trace_replay",
            "mission_id": mission_id,
            "attempt_id": attempt_id,
            "case_found": True,
            "observed_query": case.observed_query,
            "gap_code": case.gap_code,
            "effective_regime": case.effective_regime,
        }
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace_db", type=Path)
    parser.add_argument("--mission-id", required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--gap-code", required=True, choices=get_args(GapCode))
    parser.add_argument("--effective-regime", required=True, choices=get_args(SearchRegime))
    parser.add_argument("--query", required=True)
    parser.add_argument("--baseline-domain", action="append", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = build_trace_replay_report(
        args.trace_db,
        mission_id=args.mission_id,
        attempt_id=args.attempt_id,
        gap_code=args.gap_code,
        effective_regime=args.effective_regime,
        suggested_follow_up_query=args.query,
        baseline_domains=args.baseline_domain,
    )
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
