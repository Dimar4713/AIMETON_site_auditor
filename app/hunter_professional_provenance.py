from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from app.models import HuntRequest
from app.policy_fingerprint import fingerprint_model_payload


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return f"sha256:{sha256(_canonical_json(value).encode('utf-8')).hexdigest()}"


def _normalized_values(values: Sequence[object]) -> list[str]:
    return sorted(" ".join(str(item).split()) for item in values if str(item).strip())


def build_legacy_hunter_brief_snapshot_from_scope(
    *,
    region: str,
    search_zone: str | None,
    industries: Sequence[object],
    focus: Sequence[object],
) -> dict[str, Any]:
    """Build a content-addressable brief from the effective Hunter scope."""
    geographies = [" ".join(region.split())]
    if search_zone:
        geographies.append(" ".join(search_zone.split()))
    return {
        "schema": "legacy_hunter_brief.v1",
        "geographies": sorted(item for item in geographies if item),
        "industries": _normalized_values(industries),
        "focus": _normalized_values(focus),
        "entity_types": ["company"],
    }


def build_legacy_hunter_brief_snapshot(request: HuntRequest) -> dict[str, Any]:
    """Build the immutable business-scope portion of a legacy Hunter mission.

    Execution limits are deliberately excluded. The snapshot represents what is
    being researched, not how many provider calls/resources execution may use.
    Query Intelligence must already have been applied before this is called.
    """
    return build_legacy_hunter_brief_snapshot_from_scope(
        region=request.region,
        search_zone=request.search_zone,
        industries=request.industries,
        focus=request.focus,
    )


def legacy_hunter_brief_revision_from_snapshot(snapshot: Mapping[str, Any]) -> str:
    """Content-addressed revision identifier for an already-normalized brief."""
    return _digest(dict(snapshot))


def legacy_hunter_brief_revision(request: HuntRequest) -> str:
    return legacy_hunter_brief_revision_from_snapshot(build_legacy_hunter_brief_snapshot(request))


def summarize_gateway_policy(policy: Any) -> dict[str, Any]:
    """Return non-secret execution-policy facts suitable for Trace Ledger/admin diagnostics."""
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
