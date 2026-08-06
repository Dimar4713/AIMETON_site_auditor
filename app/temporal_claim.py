from __future__ import annotations

from dataclasses import dataclass

from app.temporal_lease import LeaseBlocked, LeaseConflict, TemporalLease, TemporalLeaseRepository
from app.temporal_orchestrator import TemporalDecision, TemporalState, TrustedTime
from app.temporal_reconciler import TemporalReconciler


class ClaimBlocked(RuntimeError):
    pass


class NoClaimableIntent(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TemporalWorkItem:
    wait_id: str
    mission_id: str
    holder_id: str
    lease_version: int
    lease_expires_at: str
    decision: TemporalDecision


class TemporalClaimService:
    """Select and lease one ready intent without waking or mutating mission state."""

    def __init__(
        self,
        *,
        reconciler: TemporalReconciler,
        leases: TemporalLeaseRepository,
    ) -> None:
        self._reconciler = reconciler
        self._leases = leases

    def claim_one(
        self,
        *,
        holder_id: str,
        idempotency_key: str,
        now: TrustedTime,
        ttl_seconds: int,
    ) -> TemporalWorkItem:
        if not holder_id.strip() or not idempotency_key.strip():
            raise ValueError("holder_id and idempotency_key must not be empty")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if not now.trusted:
            raise ClaimBlocked("blocked:untrusted_time")

        result = self._reconciler.reconcile(now)
        if result.state == TemporalState.BLOCKED.value:
            raise ClaimBlocked(result.reason)

        for item in result.items:
            if item.decision.state is not TemporalState.READY:
                continue
            try:
                lease = self._leases.acquire(
                    wait_id=item.wait_id,
                    holder_id=holder_id,
                    idempotency_key=idempotency_key,
                    now=now,
                    ttl_seconds=ttl_seconds,
                )
            except LeaseConflict:
                continue
            except LeaseBlocked as exc:
                raise ClaimBlocked(str(exc)) from exc
            return _to_work_item(item.mission_id, item.decision, lease)

        raise NoClaimableIntent("no_claimable_intent")


def _to_work_item(
    mission_id: str,
    decision: TemporalDecision,
    lease: TemporalLease,
) -> TemporalWorkItem:
    return TemporalWorkItem(
        wait_id=lease.wait_id,
        mission_id=mission_id,
        holder_id=lease.holder_id,
        lease_version=lease.version,
        lease_expires_at=lease.expires_at.isoformat().replace("+00:00", "Z"),
        decision=decision,
    )
