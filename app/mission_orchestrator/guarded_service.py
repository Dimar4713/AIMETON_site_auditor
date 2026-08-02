from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal

from app.mission_orchestrator.models import (
    ActionCandidate,
    ActionDecision,
    ActionType,
    MissionLifecycle,
    NextActionPlan,
    PolicySnapshot,
    StopReason,
)
from app.mission_orchestrator.service import MissionOrchestrator as BaseMissionOrchestrator


class MissionOrchestrator(BaseMissionOrchestrator):
    """Mission planner with fail-closed provider-to-deficit binding."""

    def plan(
        self,
        mission_id: str,
        *,
        deficits: list[str],
        candidates: list[ActionCandidate],
        policy: PolicySnapshot,
        now: datetime | None = None,
    ) -> NextActionPlan:
        snapshot = self.get(mission_id)
        if snapshot.lifecycle in {
            MissionLifecycle.BLOCKED,
            MissionLifecycle.COMPLETED,
        }:
            raise ValueError("terminal mission cannot be replanned")

        evaluated_at = now or datetime.now(UTC)
        effective_policy = self._effective_policy(snapshot, policy)
        active_deficits = set(deficits)
        ordered_candidates = sorted(
            candidates,
            key=lambda item: json.dumps(
                item.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )

        decisions: list[ActionDecision] = []
        for candidate in ordered_candidates:
            decision = self._evaluate_candidate(
                candidate,
                effective_policy,
                evaluated_at,
            )
            if (
                candidate.action_type == ActionType.QUERY_PROVIDER
                and candidate.deficit_code not in active_deficits
            ):
                decision = decision.model_copy(
                    update={
                        "admissible": False,
                        "reason_codes": [
                            *decision.reason_codes,
                            "deficit_not_active",
                        ],
                    }
                )
            decisions.append(decision)

        admissible = [item.candidate for item in decisions if item.admissible]
        if admissible:
            selected = min(
                admissible,
                key=lambda item: (
                    -item.expected_sufficiency_gain,
                    -item.ai_priority,
                    sum(item.estimated_cost_by_currency.values(), Decimal("0")),
                    item.estimated_latency_ms,
                    item.error_risk,
                    item.action_type.value,
                    item.target,
                ),
            )
            reason = "highest_admissible_expected_gain"
        else:
            selected = ActionCandidate(
                action_type=ActionType.STOP,
                deficit_code="policy",
            )
            reason = StopReason.POLICY_NO_ADMISSIBLE_ACTION.value

        plan = NextActionPlan(
            mission_id=mission_id,
            turn_number=len(snapshot.turns) + 1,
            input_deficits=sorted(active_deficits),
            decisions=decisions,
            selected_action=selected,
            selection_reason=reason,
        )
        with self._lock:
            current = self._missions.get(mission_id)
            if current is None:
                raise KeyError(mission_id)
            if len(current.turns) != len(snapshot.turns):
                raise ValueError("mission changed while action was planned")
            pending = self._pending_plans.get(mission_id)
            if pending is not None:
                if pending == plan:
                    return deepcopy(pending)
                raise ValueError("another plan is already pending for this turn")
            self._pending_plans[mission_id] = plan
        return deepcopy(plan)

    @staticmethod
    def _evaluate_candidate(
        candidate: ActionCandidate,
        policy: PolicySnapshot,
        evaluated_at: datetime,
    ) -> ActionDecision:
        from app.mission_orchestrator.service import PolicyGuard

        return PolicyGuard.evaluate(candidate, policy, now=evaluated_at)


_ORCHESTRATOR = MissionOrchestrator()


def get_mission_orchestrator() -> MissionOrchestrator:
    return _ORCHESTRATOR


def reset_mission_orchestrator() -> None:
    global _ORCHESTRATOR
    _ORCHESTRATOR = MissionOrchestrator()
