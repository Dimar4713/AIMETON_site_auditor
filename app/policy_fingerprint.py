from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping


def fingerprint_model_payload(value: Any) -> str:
    """Fingerprint a Pydantic model or JSON-like policy without domain imports."""
    if hasattr(value, "model_dump"):
        payload = value.model_dump(mode="json", exclude_none=False)
    elif isinstance(value, Mapping):
        payload = dict(value)
    else:
        payload = value
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}"
