from datetime import datetime, timedelta, timezone

import pytest

from app.temporal_claim import ClaimBlocked, NoClaimableIntent, TemporalClaimService
from app.temporal_lease import TemporalLeaseRepository
from app.temporal_orchestrator import TemporalIntent, TrustedTime
from app.temporal_reconciler import TemporalReconciler
from app.temporal_repository import TemporalIntentRepository

UTC = timezone.utc
BASE = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)


def trusted(at: datetime = BASE) -> TrustedTime:
    return TrustedTime(
        utc=at,
        source="chrony",
        synced=True,
        quality="trusted",
        offset_ms=0.01,
        stratum=2,
    )


def untrusted(at: datetime = BASE) -> TrustedTime:
    return TrustedTime(
        utc=at,
        source="local",
        synced=False,
        quality="degraded",
        offset_ms=999,
        stratum=16,
    )


def intent(wait_id: str, mission_id: str, *, ready: bool = True) -> TemporalIntent:
    resume = BASE - timedelta(seconds=1) if ready else BASE + timedelta(hours=1)
    return TemporalIntent(
        wait_id=wait_id,
        mission_id=mission_id,
        created_at=BASE - timedelta(hours=1),
        resume_not_before=resume,
        deadline=BASE + timedelta(hours=2),
    )


def service(tmp_path):
    intents = TemporalIntentRepository(tmp_path / "intents.sqlite3")
    leases = TemporalLeaseRepository(tmp_path / "leases.sqlite3")
    return intents, leases, TemporalClaimService(
        reconciler=TemporalReconciler(intents),
        leases=leases,
    )


def test_claims_first_ready_intent_in_stable_wait_id_order(tmp_path):
    intents, _, claims = service(tmp_path)
    intents.create(intent("wait-b", "mission-b"), idempotency_key="intent-b")
    intents.create(intent("wait-a", "mission-a"), idempotency_key="intent-a")

    item = claims.claim_one(
        holder_id="agent-1",
        idempotency_key="claim-1",
        now=trusted(),
        ttl_seconds=60,
    )

    assert item.wait_id == "wait-a"
    assert item.mission_id == "mission-a"
    assert item.holder_id == "agent-1"


def test_skips_candidate_held_by_other_agent(tmp_path):
    intents, leases, claims = service(tmp_path)
    intents.create(intent("wait-a", "mission-a"), idempotency_key="intent-a")
    intents.create(intent("wait-b", "mission-b"), idempotency_key="intent-b")
    leases.acquire(
        wait_id="wait-a",
        holder_id="agent-other",
        idempotency_key="other-claim",
        now=trusted(),
        ttl_seconds=60,
    )

    item = claims.claim_one(
        holder_id="agent-1",
        idempotency_key="claim-1",
        now=trusted(),
        ttl_seconds=60,
    )

    assert item.wait_id == "wait-b"


def test_repeat_returns_same_work_item_and_lease_version(tmp_path):
    intents, _, claims = service(tmp_path)
    intents.create(intent("wait-a", "mission-a"), idempotency_key="intent-a")

    first = claims.claim_one(
        holder_id="agent-1",
        idempotency_key="claim-1",
        now=trusted(),
        ttl_seconds=60,
    )
    second = claims.claim_one(
        holder_id="agent-1",
        idempotency_key="claim-1",
        now=trusted(),
        ttl_seconds=60,
    )

    assert second == first


def test_untrusted_time_blocks_before_lease_mutation(tmp_path):
    intents, leases, claims = service(tmp_path)
    intents.create(intent("wait-a", "mission-a"), idempotency_key="intent-a")

    with pytest.raises(ClaimBlocked, match="blocked:untrusted_time"):
        claims.claim_one(
            holder_id="agent-1",
            idempotency_key="claim-1",
            now=untrusted(),
            ttl_seconds=60,
        )

    assert leases.get("wait-a") is None


def test_no_ready_candidate_returns_typed_result(tmp_path):
    intents, leases, claims = service(tmp_path)
    intents.create(intent("wait-a", "mission-a", ready=False), idempotency_key="intent-a")

    with pytest.raises(NoClaimableIntent, match="no_claimable_intent"):
        claims.claim_one(
            holder_id="agent-1",
            idempotency_key="claim-1",
            now=trusted(),
            ttl_seconds=60,
        )

    assert leases.get("wait-a") is None
