from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.mission_observability import derive_runtime_observation, observe_gap


def record(*, status: str, created_at: str):
    return {
        "kind": "turn",
        "payload": {"status": status, "summary": "safe"},
        "created_at": created_at,
    }


def test_running_event_is_fresh_within_bound() -> None:
    observed = derive_runtime_observation(
        [record(status="running", created_at="2026-08-03T00:00:00+00:00")],
        now=datetime(2026, 8, 3, 0, 1, tzinfo=timezone.utc),
        stall_after_seconds=90,
    )
    assert observed.heartbeat_status == "fresh"
    assert observed.stalled is False
    assert observed.reason_code is None


def test_running_event_becomes_typed_stalled_after_bound() -> None:
    observed = derive_runtime_observation(
        [record(status="running", created_at="2026-08-03T00:00:00+00:00")],
        now=datetime(2026, 8, 3, 0, 2, tzinfo=timezone.utc),
        stall_after_seconds=90,
    )
    assert observed.heartbeat_status == "stalled"
    assert observed.stalled is True
    assert observed.reason_code == "heartbeat_stalled"


def test_terminal_event_is_not_marked_stalled() -> None:
    observed = derive_runtime_observation(
        [record(status="blocked", created_at="2026-08-02T00:00:00+00:00")],
        now=datetime(2026, 8, 3, 0, 0, tzinfo=timezone.utc),
    )
    assert observed.heartbeat_status == "not_applicable"
    assert observed.stalled is False


def test_missing_valid_timestamp_is_typed_without_guessing() -> None:
    observed = derive_runtime_observation([{"payload": {"status": "running"}}])
    assert observed.heartbeat_status == "missing"
    assert observed.reason_code == "heartbeat_missing"
    assert observed.stalled is False


def test_invalid_bound_is_rejected() -> None:
    with pytest.raises(ValueError):
        derive_runtime_observation([], stall_after_seconds=0)


@pytest.mark.parametrize(
    "reason",
    ["not_searched", "not_found_after_sufficient_search", "blocked", "degraded"],
)
def test_gap_reasons_remain_distinct_and_fail_closed(reason: str) -> None:
    observation = observe_gap(
        mission_id="mission-1",
        reason=reason,
        component="company_profile",
        field_key="contacts.phone",
        latency_ms=120,
        retry_count=1,
        cache_hit=False,
        attempted_cost=0.02,
        billed_cost=0.01,
        accepted_cost=0,
    )
    assert observation.reason == reason
    assert observation.client_release_eligible is False


def test_gap_observation_contains_only_safe_operational_metadata() -> None:
    observation = observe_gap(
        mission_id="mission-1",
        reason="degraded",
        component="provider_gateway",
        field_key="revenue.value",
        latency_ms=42,
    )
    payload = observation.model_dump(mode="json")
    serialized = str(payload)
    for forbidden in ("url", "query", "document", "prompt", "secret", "token", "raw"):
        assert forbidden not in serialized.lower()
    assert set(payload["metadata"]) == {
        "component",
        "field_key",
        "latency_ms",
        "retry_count",
        "cache_hit",
        "attempted_cost",
        "billed_cost",
        "accepted_cost",
    }


def test_unsafe_identifiers_are_rejected_instead_of_logged() -> None:
    with pytest.raises(ValidationError):
        observe_gap(
            mission_id="mission-1",
            reason="blocked",
            component="provider?token=secret",
            field_key="contacts.phone",
        )
