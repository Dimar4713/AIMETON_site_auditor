from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from app.models import HuntRequest


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return f"sha256:{sha256(_canonical_json(value).encode('utf-8')).hexdigest()}"


def build_legacy_hunter_brief_snapshot(request: HuntRequest) -> dict[str, Any]:
    """Build the immutable business-scope portion of a legacy Hunter mission.

    Execution limits are deliberately excluded. The snapshot represents what is
    being researched, not how many provider calls/resources execution may use.
    Query Intelligence must already have been applied before this is called.
    """
    geographies = [" ".join(request.region.split())]
    if request.search_zone:
        geographies.append(" ".join(request.search_zone.split()))
    return {
        "schema": "legacy_hunter_brief.v1",
        "geographies": sorted(geographies),
        "industries": sorted(" ".join(item.split()) for item in request.industries),
        "focus": sorted(" ".join(item.split()) for item in request.focus),
        "entity_types": ["company"],
    }


def legacy_hunter_brief_revision(request: HuntRequest) -> str:
    """Content-addressed revision identifier for an effective Hunter brief."""
    return _digest(build_legacy_hunter_brief_snapshot(request))


def fingerprint_model_payload(value: Any) -> str:
    """Fingerprint a Pydantic/model or JSON-like policy without exposing values."""
    if hasattr(value, "model_dump"):
        payload = value.model_dump(mode="json", exclude_none=False)
    elif isinstance(value, Mapping):
        payload = dict(value)
    else:
        payload = value
    return _digest(payload)


def summarize_gateway_policy(policy: Any) -> dict[str, Any]:
    """Return non-secret execution-policy facts suitable for Trace Ledger."""
    return {
        "fingerprint": fingerprint_model_payload(policy),
        "provider_order": list(policy.provider_order),
        "allowed_providers": sorted(policy.allowed_providers),
        "strategy": str(policy.strategy),
        "target_results": int(policy.target_results),
        "max_providers_per_query": int(policy.max_providers_per_query),
        "allow_paid_fallback": bool(policy.allow_paid_fallback),
        "allow_paid_fanout": bool(policy.allow_paid_fanout),
        "max_cost_by_currency": {
            str(key): str(value)
            for key, value in sorted(policy.max_cost_by_currency.items())
        },
    }
