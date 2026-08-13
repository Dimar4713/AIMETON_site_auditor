#!/usr/bin/env python3
"""Build a reproducible offline Search Observer calibration replay bundle.

The bundle records SHA-256 provenance for each retained evidence file and embeds
calibration diagnostics. It performs no provider/LLM calls, changes no routing,
and defines no promotion threshold.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.search_observer_calibration_diagnostics import build_diagnostics


def _load_evidence(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("calibration_replay_requires_object_evidence")
    provenance = {
        "name": path.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "schema_version": payload.get("schema_version"),
        "scenario_count": len(payload.get("scenarios", [])),
    }
    return payload, provenance


def build_replay_bundle(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        raise ValueError("calibration_replay_requires_evidence")

    payloads: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []
    for path in paths:
        payload, record = _load_evidence(path)
        payloads.append(payload)
        provenance.append(record)

    return {
        "bundle_schema_version": 1,
        "evidence_kind": "search_observer_calibration_replay_bundle",
        "evidence_files": provenance,
        "diagnostics": build_diagnostics(payloads),
        "routing_changed": False,
        "steering_enabled": False,
        "promotion_eligible": False,
        "reason_code": "offline_replay_bundle_not_promotion_gate",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    bundle = build_replay_bundle(args.evidence)
    text = json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
