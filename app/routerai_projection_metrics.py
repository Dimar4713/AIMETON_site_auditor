from __future__ import annotations

import json
from typing import Any

from app.routerai_evidence_units import project_sources
from app.routerai_profile_extraction import (
    _IDENTITY_CORE_KINDS,
    _MANAGEMENT_KINDS,
    _OPERATIONS_KINDS,
    _OWNERSHIP_NETWORK_KINDS,
    _SIGNAL_KINDS,
    _SLICE_SOURCE_KEYS,
)


_SLICE_KINDS = (
    _IDENTITY_CORE_KINDS,
    _MANAGEMENT_KINDS,
    _OWNERSHIP_NETWORK_KINDS,
    _OPERATIONS_KINDS,
    _SIGNAL_KINDS,
)


def _compact_json_chars(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def routerai_projection_metrics(sources: list[dict[str, Any]]) -> dict[str, int]:
    """Measure split-v2 external evidence duplication without retaining content."""
    if not sources:
        return {
            "projected_external_chars_total": 0,
            "projected_external_source_refs_total": 0,
            "unique_projected_external_chars": 0,
            "projection_duplication_ratio_x1000": 0,
        }

    projected_slices = [
        project_sources(sources, kinds, _SLICE_SOURCE_KEYS)
        for kinds in _SLICE_KINDS
    ]
    projected_chars_total = sum(_compact_json_chars(items) for items in projected_slices)
    projected_source_refs_total = sum(len(items) for items in projected_slices)

    unique_projected = project_sources(
        sources,
        {str(source.get("query_kind") or "unknown") for source in sources},
        _SLICE_SOURCE_KEYS,
    )
    unique_projected_chars = _compact_json_chars(unique_projected)
    duplication_ratio_x1000 = (
        round(projected_chars_total * 1000 / unique_projected_chars)
        if unique_projected_chars > 0
        else 0
    )

    return {
        "projected_external_chars_total": projected_chars_total,
        "projected_external_source_refs_total": projected_source_refs_total,
        "unique_projected_external_chars": unique_projected_chars,
        "projection_duplication_ratio_x1000": duplication_ratio_x1000,
    }
