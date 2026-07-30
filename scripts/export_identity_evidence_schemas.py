#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.identity_evidence.models import (
    IdentityEvidenceResult,
    IdentitySearchResult,
)


TARGETS = {
    ROOT / "schemas" / "identity-search-v0.1.schema.json": IdentitySearchResult,
    ROOT / "schemas" / "identity-evidence-v0.1.schema.json": IdentityEvidenceResult,
}


def render_schema(model) -> str:
    schema = model.model_json_schema(ref_template="#/$defs/{model}")
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> None:
    for target, model in TARGETS.items():
        target.write_text(render_schema(model), encoding="utf-8")


if __name__ == "__main__":
    main()
