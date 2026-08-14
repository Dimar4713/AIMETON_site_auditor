#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.search_gap_query_replay import GapQueryReplayCase
from app.search_gap_retained_evidence import build_gap_hindsight_report


def build_replay_report(payload: object) -> dict[str, object]:
    raw_cases = payload.get("cases", payload) if isinstance(payload, dict) else payload
    if not isinstance(raw_cases, list):
        raise ValueError("gap_query_replay_requires_case_list")
    cases = [GapQueryReplayCase.model_validate(item) for item in raw_cases]
    retained = [case.to_retained_outcome() for case in cases]
    report = build_gap_hindsight_report(retained)
    report["evidence_kind"] = "search_gap_query_replay"
    report["case_count"] = len(cases)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    payload = json.loads(args.evidence.read_text(encoding="utf-8"))
    report = build_replay_report(payload)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
