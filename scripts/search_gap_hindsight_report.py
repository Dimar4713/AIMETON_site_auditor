#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.search_gap_retained_evidence import RetainedGapOutcome, build_gap_hindsight_report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    payload = json.loads(args.evidence.read_text(encoding="utf-8"))
    raw_records = payload.get("records", payload) if isinstance(payload, dict) else payload
    if not isinstance(raw_records, list):
        raise ValueError("gap_hindsight_evidence_requires_record_list")
    records = [RetainedGapOutcome.model_validate(item) for item in raw_records]
    report = build_gap_hindsight_report(records)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
