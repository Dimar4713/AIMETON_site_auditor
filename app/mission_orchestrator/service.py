from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from threading import RLock
from urllib.parse import urlsplit
from uuid import uuid4

from app.mission_orchestrator.models import (
    ActionCandidate,
    ActionDecision,
    ActionOutcome,
    ActionOutcomeState,
    ActionType,
    EntryPoint,
    MissionContract,
    MissionCreateRequest,
    MissionQuestion,
    MissionLifecycle,
    MissionSnapshot,
    NextActionPlan,
    PolicySnapshot,
    QuestionState,
    StopReason,
    SufficiencyFeedback,
    SufficiencyLevel,
    TurnTrace,
)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _level_value(level: SufficiencyLevel) -> int:
    return int(level.value[1:])


def mission_contract_fingerprint(request: MissionCreateRequest) -> str:
    payload = {
        "target_url": str(request.target_url),
        "goal": " ".join(request.goal.split()),
        "target_sufficiency": request.target_sufficiency.value,
        "questions": [
            item.model_dump(mode="json")
            for item in sorted(request.questions, key=lambda item: item.code)
        ],
        "budget": request.budget.model_dump(mode="json"),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def default_site_mission_request(
    url: str,
    *,
    analysis_id: str | None = None,
) -> MissionCreateRequest:
    return MissionCreateRequest(
        target_url=url,
        goal="Build a source-traceable company profile and identify AI opportunities.",
        target_sufficiency=SufficiencyLevel.L4,
        questions=[
            MissionQuestion(code=code, freshness_days=days)
            for code, days in (
                ("identity", 30),
                ("contacts", 30),
                ("workforce", 180),
                ("financials", 365),
                ("ownership", 180),
                ("legal_events", 30),
            )
        ],
        analysis_id=analysis_id,
    )


class PolicyGuard:
    @staticmethod
    def _host_allowed(candidate: ActionCandidate, policy: PolicySnapshot) -> bool:
        if candidate.action_type not in {
            ActionType.CRAWL_URL,
            ActionType.FETCH_DOCUMENT,
        }:
            return True
        host = (urlsplit(candidate.target).hostname or "").lower()
        return bool(host) and bool(policy.allowed_hosts) and host in policy.allowed_hosts

    @staticmethod
    def evaluate(
        candidate: ActionCandidate,
        policy: PolicySnapshot,
        *,
        now: datetime,
    ) -> ActionDecision:
        reasons: list[str] = []
        if candidate.action_type not in policy.allowed_action_types:
            reasons.append("action_type_blocked")
        if policy.remaining_actions < 1 and candidate.action_type != ActionType.STOP:
            reasons.append("action_budget_exhausted")
        if policy.deadline_at is not None and now >= policy.deadline_at:
            reasons.append("deadline_exceeded")
        if not candidate.robots_allowed:
            reasons.append("robots_blocked")
        if not candidate.ssrf_validated:
            reasons.append("ssrf_blocked")
        if not candidate.rights_allowed:
            reasons.append("rights_blocked")
        if not candidate.rate_limit_allowed:
            reasons.append("rate_limit_blocked")
        if not PolicyGuard._host_allowed(candidate, policy):
            reasons.append("domain_blocked")
        for currency, amount in candidate.estimated_cost_by_currency.items():
            remaining = policy.remaining_cost_by_currency.get(currency)
            if amount > 0 and (remaining is None or amount > remaining):
                reasons.append(f"budget_blocked:{currency}")
        return ActionDecision(
            candidate=candidate,
            admissible=not reasons,
            reason_codes=reasons,
        )


class MissionOrchestrator:
    def __init__(self) -> None:
        self._missions: dict[str, MissionSnapshot] = {}
        self._pending_plans: dict[str, NextActionPlan] = {}
        self._lock = RLock()

    @staticmethod
    def _spent(snapshot: MissionSnapshot) -> dict[str, Decimal]:
        spent: dict[str, Decimal] = {}
        for turn in snapshot.turns:
            for currency, amount in turn.outcome.actual_cost_by_currency.items():
                spent[currency] = spent.get(currency, Decimal("0")) + amount
        return spent

    @staticmethod
    def _budget_exceeded(snapshot: MissionSnapshot) -> bool:
        spent = MissionOrchestrator._spent(snapshot)
        limits = snapshot.contract.budget.max_cost_by_currency
        return any(
            currency not in limits or amount > limits[currency]
            for currency, amount in spent.items()
            if amount > 0
        )

    @staticmethod
    def _effective_policy(
        snapshot: MissionSnapshot,
        requested: PolicySnapshot,
    ) -> PolicySnapshot:
        spent = MissionOrchestrator._spent(snapshot)

        contract_remaining = {
            currency: max(Decimal("0"), limit - spent.get(currency, Decimal("0")))
            for currency, limit in snapshot.contract.budget.max_cost_by_currency.items()
        }
        effective_remaining: dict[str, Decimal] = {}
        for currency in set(contract_remaining) | set(
            requested.remaining_cost_by_currency
        ):
            contract_amount = contract_remaining.get(currency)
            requested_amount = requested.remaining_cost_by_currency.get(currency)
            effective_remaining[currency] = (
                Decimal("0")
                if contract_amount is None or requested_amount is None
                else min(contract_amount, requested_amount)
            )

        deadlines = [
            item
            for item in (
                snapshot.contract.budget.deadline_at,
                requested.deadline_at,
            )
            if item is not None
        ]
        return PolicySnapshot(
            allowed_action_types=requested.allowed_action_types,
            allowed_hosts=requested.allowed_hosts,
            remaining_cost_by_currency=effective_remaining,
            remaining_actions=min(
                requested.remaining_actions,
                max(
                    0,
                    snapshot.contract.budget.max_actions - len(snapshot.turns),
                ),
            ),
            deadline_at=min(deadlines) if deadlines else None,
        )

    def create_mission(
        self,
        request: MissionCreateRequest,
        *,
        entry_point: EntryPoint,
    ) -> MissionSnapshot:
        now = datetime.now(UTC)
        mission_id = _id("mission")
        analysis_id = request.analysis_id or _id("analysis")
        contract = MissionContract(
            mission_id=mission_id,
            analysis_id=analysis_id,
            correlation_id=_id("corr"),
            entry_point=entry_point,
            target_url=request.target_url,
            goal=request.goal,
            target_sufficiency=request.target_sufficiency,
            questions=request.questions,
            budget=request.budget,
            contract_fingerprint=mission_contract_fingerprint(request),
            created_at=now,
        )
        snapshot = MissionSnapshot(
            contract=contract,
            lifecycle=MissionLifecycle.PLANNED,
            question_states={
                item.code: QuestionState.NOT_SEARCHED for item in request.questions
            },
        )
        with self._lock:
            if any(
                item.contract.analysis_id == analysis_id
                for item in self._missions.values()
            ):
                raise ValueError("analysis_id already belongs to another mission")
            self._missions[mission_id] = snapshot
        return deepcopy(snapshot)

    def get(self, mission_id: str) -> MissionSnapshot:
        with self._lock:
            snapshot = self._missions.get(mission_id)
            if snapshot is None:
                raise KeyError(mission_id)
            return deepcopy(snapshot)

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
        ordered_candidates = sorted(
            candidates,
            key=lambda item: json.dumps(
                item.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        decisions = [
            PolicyGuard.evaluate(candidate, effective_policy, now=evaluated_at)
            for candidate in ordered_candidates
        ]
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
            input_deficits=sorted(set(deficits)),
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

    def record_turn(
        self,
        mission_id: str,
        *,
        plan: NextActionPlan,
        outcome: ActionOutcome,
        feedback: SufficiencyFeedback,
        recorded_at: datetime | None = None,
    ) -> MissionSnapshot:
        with self._lock:
            snapshot = self._missions.get(mission_id)
            if snapshot is None:
                raise KeyError(mission_id)
            if plan.mission_id != mission_id:
                raise ValueError("plan belongs to another mission")
            if plan.turn_number != len(snapshot.turns) + 1:
                raise ValueError("turn number is not sequential")
            if self._pending_plans.get(mission_id) != plan:
                raise ValueError("plan was not issued by this orchestrator")
            unknown = set(feedback.question_states) - set(snapshot.question_states)
            if unknown:
                raise ValueError(f"feedback contains unknown questions: {sorted(unknown)}")

            before = snapshot.achieved_sufficiency
            snapshot.question_states.update(feedback.question_states)
            snapshot.achieved_sufficiency = feedback.achieved
            snapshot.artifact_refs = list(
                dict.fromkeys([*snapshot.artifact_refs, *outcome.artifact_refs])
            )
            trace = TurnTrace(
                mission_id=mission_id,
                turn_number=plan.turn_number,
                before_sufficiency=before,
                input_deficits=plan.input_deficits,
                decisions=plan.decisions,
                selected_action=plan.selected_action,
                outcome=outcome,
                after_sufficiency=feedback.achieved,
                resulting_gaps=feedback.critical_gaps,
                recorded_at=recorded_at or datetime.now(UTC),
            )
            snapshot.turns.append(trace)

            invalid_completion = (
                feedback.stop_reason == StopReason.SUFFICIENCY_REACHED
                and (
                    _level_value(feedback.achieved)
                    < _level_value(snapshot.contract.target_sufficiency)
                    or any(
                        snapshot.question_states[item.code]
                        == QuestionState.NOT_SEARCHED
                        for item in snapshot.contract.questions
                        if item.required
                    )
                )
            )
            if self._budget_exceeded(snapshot):
                snapshot.lifecycle = MissionLifecycle.BLOCKED
                snapshot.stop_reason = StopReason.BUDGET_EXHAUSTED
            elif invalid_completion:
                snapshot.lifecycle = MissionLifecycle.BLOCKED
                snapshot.stop_reason = StopReason.INVALID_COMPLETION
            elif feedback.stop_reason is not None:
                snapshot.stop_reason = feedback.stop_reason
                snapshot.lifecycle = (
                    MissionLifecycle.COMPLETED
                    if feedback.stop_reason == StopReason.SUFFICIENCY_REACHED
                    else MissionLifecycle.BLOCKED
                )
            elif plan.selected_action.action_type == ActionType.STOP:
                snapshot.lifecycle = MissionLifecycle.BLOCKED
                snapshot.stop_reason = StopReason.POLICY_NO_ADMISSIBLE_ACTION
            elif outcome.state == ActionOutcomeState.FAILED:
                snapshot.lifecycle = MissionLifecycle.DEGRADED
            else:
                snapshot.lifecycle = MissionLifecycle.RUNNING
            self._missions[mission_id] = snapshot
            self._pending_plans.pop(mission_id, None)
            return deepcopy(snapshot)


_ORCHESTRATOR = MissionOrchestrator()


def get_mission_orchestrator() -> MissionOrchestrator:
    return _ORCHESTRATOR


def reset_mission_orchestrator() -> None:
    global _ORCHESTRATOR
    _ORCHESTRATOR = MissionOrchestrator()


def record_legacy_site_turn(
    orchestrator: MissionOrchestrator,
    mission_id: str,
    *,
    final_url: str,
    succeeded: bool,
) -> MissionSnapshot:
    host = (urlsplit(final_url).hostname or "").lower()
    candidate = ActionCandidate(
        action_type=ActionType.FETCH_DOCUMENT,
        target=final_url,
        deficit_code="bootstrap",
        expected_sufficiency_gain=0.1,
        ai_priority=0.5,
    )
    plan = orchestrator.plan(
        mission_id,
        deficits=["identity", "contacts"],
        candidates=[candidate],
        policy=PolicySnapshot(
            allowed_hosts=frozenset({host}),
            remaining_actions=1,
        ),
    )
    snapshot = orchestrator.get(mission_id)
    return orchestrator.record_turn(
        mission_id,
        plan=plan,
        outcome=ActionOutcome(
            state=(
                ActionOutcomeState.PARTIAL
                if succeeded
                else ActionOutcomeState.FAILED
            ),
            artifact_refs=[final_url] if succeeded else [],
            reason_codes=["legacy_adapter_preliminary"],
        ),
        feedback=SufficiencyFeedback(
            achieved=SufficiencyLevel.L0,
            question_states=snapshot.question_states,
            critical_gaps=["identity", "contacts"],
        ),
    )
