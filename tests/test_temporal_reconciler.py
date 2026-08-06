from datetime import datetime, timezone

from app.temporal_orchestrator import TemporalIntent, TemporalState, TrustedTime
from app.temporal_reconciler import TemporalReconciler
from app.temporal_repository import TemporalIntentRepository


UTC = timezone.utc


def _time(hour: int, *, trusted: bool = True) -> TrustedTime:
    return TrustedTime(
        utc=datetime(2026, 8, 6, hour, tzinfo=UTC),
        source="chrony" if trusted else "system_clock",
        synced=trusted,
        quality="trusted" if trusted else "fallback",
        offset_ms=0.1,
        stratum=2,
    )


def _intent(wait_id: str, resume_hour: int, deadline_hour: int) -> TemporalIntent:
    return TemporalIntent(
        wait_id=wait_id,
        mission_id=f"mission-{wait_id}",
        created_at=datetime(2026, 8, 6, 10, tzinfo=UTC),
        resume_not_before=datetime(2026, 8, 6, resume_hour, tzinfo=UTC),
        deadline=datetime(2026, 8, 6, deadline_hour, tzinfo=UTC),
    )


def test_reconcile_is_stable_and_read_only(tmp_path) -> None:
    repo = TemporalIntentRepository(tmp_path / "temporal.sqlite3")
    repo.create(_intent("b", 15, 18), idempotency_key="b")
    repo.create(_intent("a", 13, 14), idempotency_key="a")
    reconciler = TemporalReconciler(repo)

    first = reconciler.reconcile(_time(14))
    second = reconciler.reconcile(_time(14))

    assert first == second
    assert [item.wait_id for item in first.items] == ["a", "b"]
    assert first.items[0].decision.state is TemporalState.TIMED_OUT
    assert first.items[1].decision.state is TemporalState.WAITING
    assert repo.get("a").version == 1
    assert repo.get("b").version == 1


def test_untrusted_time_blocks_entire_cycle_without_read_results(tmp_path) -> None:
    repo = TemporalIntentRepository(tmp_path / "temporal.sqlite3")
    repo.create(_intent("a", 13, 14), idempotency_key="a")

    result = TemporalReconciler(repo).reconcile(_time(14, trusted=False))

    assert result.state == TemporalState.BLOCKED.value
    assert result.reason == "blocked:untrusted_time"
    assert result.items == ()
    assert repo.get("a").version == 1


def test_ready_intent_is_reported_without_wake_side_effect(tmp_path) -> None:
    repo = TemporalIntentRepository(tmp_path / "temporal.sqlite3")
    repo.create(_intent("ready", 12, 16), idempotency_key="ready")

    result = TemporalReconciler(repo).reconcile(_time(13))

    assert result.items[0].decision.state is TemporalState.READY
    assert repo.get("ready").version == 1
