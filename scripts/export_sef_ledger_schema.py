#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.sef.ledger import LedgerContract


TARGET = ROOT / "schemas" / "sef-ledger-v0.1.schema.json"


def render_schema() -> str:
    schema = LedgerContract.model_json_schema(ref_template="#/$defs/{model}")
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> None:
    TARGET.write_text(render_schema(), encoding="utf-8")


if __name__ == "__main__":
    main()
