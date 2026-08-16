from __future__ import annotations

from copy import deepcopy

from app.hunter_forensic_trace import HunterForensicTrace
from app.hunter_professional_provenance import (
    build_legacy_hunter_brief_snapshot_from_scope,
    fingerprint_model_payload,
    legacy_hunter_brief_revision_from_snapshot,
    summarize_gateway_policy,
)
from app.search_gateway.models import SearchPolicy, SearchStrategy
from app.trace_ledger import RetentionClass, TraceState


def test_effective_scope_revision_is_order_stable() -> None:
    first = build_legacy_hunter_brief_snapshot_from_scope(
        region=" Красноярск ",
        search_zone=None,
        industries=["Стоматология", "Медицина"],
        focus=["B2B", "частные клиники"],
    )
    second = build_legacy_hunter_brief_snapshot_from_scope(
        region="Красноярск",
        search_zone=None,
        industries=["Медицина", "Стоматология"],
        focus=["частные  клиники", "B2B"],
    )

    assert first == second
    assert legacy_hunter_brief_revision_from_snapshot(first) == legacy_hunter_brief_revision_from_snapshot(second)


def test_policy_fingerprint_changes_when_execution_semantics_change() -> None:
    base = SearchPolicy(
        provider_order=("searxng", "yandex"),
        allowed_providers=frozenset({"searxng", "yandex"}),
        strategy=SearchStrategy.FALLBACK_FIRST_NONEMPTY,
        target_results=10,
        max_providers_per_query=2,
    )
    changed = base.model_copy(update={"provider_order": ("yandex", "searxng")})

    assert fingerprint_model_payload(base) != fingerprint_model_payload(changed)
    assert summarize_gateway_policy(base)["provider_order"] == ["searxng", "yandex"]


def test_hunt_plan_retains_non_authoritative_trace_bridge(tmp_path) -> None:
    trace = HunterForensicTrace(
        "hunt-test",
        "attempt-test",
        trace_db_path=tmp_path / "trace.sqlite3",
    )
    metadata = {
        "plan_source": "deterministic_fallback",
        "effective_region": "Красноярск",
        "effective_industries": ["Стоматология"],
        "effective_focus": ["B2B"],
    }

    trace.append(
        "hunt_plan",
        state=TraceState.SUCCEEDED,
        reason_code="hunter_query_plan_built",
        summary="test",
        metadata=deepcopy(metadata),
    )

    events = trace.ledger.list_attempt("hunt-test", "attempt-test")
    bridge = next(
        event
        for event in events
        if event.component == "professional_configuration_bridge"
        and event.operation == "legacy_hunter_brief_resolved"
    )
    forensic = next(event for event in events if event.component == "hunter" and event.operation == "hunt_plan")

    assert bridge.retention_class is RetentionClass.TRACE
    assert forensic.retention_class is RetentionClass.FORENSIC
    assert bridge.metadata["authoritative_product_state"] is False
    assert str(bridge.metadata["brief_revision"]).startswith("sha256:")
    assert bridge.metadata["geographies"] == ["Красноярск"]
    assert bridge.metadata["industries"] == ["Стоматология"]
    assert bridge.metadata["routing_changed"] is False
