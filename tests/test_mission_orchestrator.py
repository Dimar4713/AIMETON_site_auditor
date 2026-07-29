from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.mission_orchestrator import (
    ActionCandidate,
    ActionOutcome,
    ActionOutcomeState,
    ActionType,
    EntryPoint,
    MissionLifecycle,
    MissionOrchestrator,
    MissionQuestion,
    PolicySnapshot,
    QuestionState,
    StopReason,
    SufficiencyFeedback,
    SufficiencyLevel,
    default_site_mission_request,
)


def create(orchestrator: MissionOrchestrator, entry_point=EntryPoint.REST):
    return orchestrator.create_mission(
        default_site_mission_request("https://example.test/"),
        entry_point=entry_point,
    )


def test_ui_rest_and_mcp_build_equivalent_contracts_with_isolated_ids():
    orchestrator = MissionOrchestrator()

    snapshots = [
        create(orchestrator, entry_point)
        for entry_point in (EntryPoint.UI, EntryPoint.REST, EntryPoint.MCP)
    ]

    assert len({item.contract.mission_id for item in snapshots}) == 3
    assert len({item.contract.analysis_id for item in snapshots}) == 3
    assert len({item.contract.correlation_id for item in snapshots}) == 3
    assert len({item.contract.contract_fingerprint for item in snapshots}) == 1
    assert all(item.lifecycle == MissionLifecycle.PLANNED for item in snapshots)
    assert all(
        set(item.question_states.values()) == {QuestionState.NOT_SEARCHED}
        for item in snapshots
    )


def test_policy_guard_is_deterministic_and_ai_cannot_select_blocked_action():
    orchestrator = MissionOrchestrator()
    mission = create(orchestrator)
    candidates = [
        ActionCandidate(
            action_type=ActionType.CRAWL_URL,
            target="https://example.test/contacts",
            deficit_code="contacts",
            expected_sufficiency_gain=0.6,
            ai_priority=0.9,
        ),
        ActionCandidate(
            action_type=ActionType.CRAWL_URL,
            target="https://forbidden.test/private",
            deficit_code="identity",
            expected_sufficiency_gain=1,
            ai_priority=1,
        ),
        ActionCandidate(
            action_type=ActionType.QUERY_PROVIDER,
            target="company registry query",
            deficit_code="identity",
            expected_sufficiency_gain=0.8,
            ai_priority=0.8,
            estimated_cost_by_currency={"RUB": Decimal("2")},
        ),
        ActionCandidate(
            action_type=ActionType.FETCH_DOCUMENT,
            target="https://example.test/blocked.pdf",
            deficit_code="ownership",
            expected_sufficiency_gain=0.9,
            robots_allowed=False,
        ),
    ]
    policy = PolicySnapshot(
        allowed_hosts=frozenset({"example.test"}),
        remaining_cost_by_currency={"RUB": Decimal("1")},
        remaining_actions=4,
        deadline_at=datetime.now(UTC) + timedelta(minutes=5),
    )

    first = orchestrator.plan(
        mission.contract.mission_id,
        deficits=["contacts", "identity"],
        candidates=candidates,
        policy=policy,
    )
    second = orchestrator.plan(
        mission.contract.mission_id,
        deficits=["identity", "contacts"],
        candidates=list(reversed(candidates)),
        policy=policy,
    )

    assert first == second
    assert first.selected_action.target == "https://example.test/contacts"
    reasons = {
        item.candidate.target: item.reason_codes
        for item in first.decisions
        if not item.admissible
    }
    assert reasons["https://forbidden.test/private"] == ["domain_blocked"]
    assert reasons["company registry query"] == ["budget_blocked:RUB"]
    assert reasons["https://example.test/blocked.pdf"] == ["robots_blocked"]


def test_contract_budget_caps_caller_policy_and_accumulates_actual_spend():
    orchestrator = MissionOrchestrator()
    request = default_site_mission_request("https://example.test/")
    request.budget.max_cost_by_currency = {"RUB": Decimal("2")}
    mission = orchestrator.create_mission(request, entry_point=EntryPoint.REST)
    mission_id = mission.contract.mission_id
    policy = PolicySnapshot(
        remaining_cost_by_currency={"RUB": Decimal("100")},
        remaining_actions=100,
    )
    first_candidate = ActionCandidate(
        action_type=ActionType.QUERY_PROVIDER,
        target="registry",
        estimated_cost_by_currency={"RUB": Decimal("1.5")},
    )
    first_plan = orchestrator.plan(
        mission_id,
        deficits=["identity"],
        candidates=[first_candidate],
        policy=policy,
    )
    assert first_plan.selected_action == first_candidate
    orchestrator.record_turn(
        mission_id,
        plan=first_plan,
        outcome=ActionOutcome(
            state=ActionOutcomeState.PARTIAL,
            actual_cost_by_currency={"RUB": Decimal("1.5")},
        ),
        feedback=SufficiencyFeedback(
            question_states={"identity": QuestionState.PARTIALLY_VERIFIED},
            critical_gaps=["identity"],
        ),
    )

    second_plan = orchestrator.plan(
        mission_id,
        deficits=["identity"],
        candidates=[
            ActionCandidate(
                action_type=ActionType.QUERY_PROVIDER,
                target="registry second page",
                estimated_cost_by_currency={"RUB": Decimal("1")},
            )
        ],
        policy=policy,
    )

    assert second_plan.selected_action.action_type == ActionType.STOP
    assert second_plan.decisions[0].reason_codes == ["budget_blocked:RUB"]


def test_turn_rejects_plan_not_issued_by_orchestrator():
    orchestrator = MissionOrchestrator()
    mission = create(orchestrator)
    plan = orchestrator.plan(
        mission.contract.mission_id,
        deficits=["identity"],
        candidates=[
            ActionCandidate(
                action_type=ActionType.RESOLVE_IDENTITY,
                deficit_code="identity",
            )
        ],
        policy=PolicySnapshot(),
    )
    forged = plan.model_copy(
        update={
            "selected_action": ActionCandidate(
                action_type=ActionType.STOP,
                deficit_code="forged",
            )
        }
    )

    try:
        orchestrator.record_turn(
            mission.contract.mission_id,
            plan=forged,
            outcome=ActionOutcome(state=ActionOutcomeState.SUCCEEDED),
            feedback=SufficiencyFeedback(
                question_states={"identity": QuestionState.VERIFIED}
            ),
        )
    except ValueError as exc:
        assert str(exc) == "plan was not issued by this orchestrator"
    else:
        raise AssertionError("forged plan was accepted")


def test_pending_plan_is_idempotent_but_cannot_be_replaced():
    orchestrator = MissionOrchestrator()
    mission = create(orchestrator)
    first = orchestrator.plan(
        mission.contract.mission_id,
        deficits=["identity"],
        candidates=[
            ActionCandidate(
                action_type=ActionType.RESOLVE_IDENTITY,
                deficit_code="identity",
            )
        ],
        policy=PolicySnapshot(),
    )
    repeated = orchestrator.plan(
        mission.contract.mission_id,
        deficits=["identity"],
        candidates=[
            ActionCandidate(
                action_type=ActionType.RESOLVE_IDENTITY,
                deficit_code="identity",
            )
        ],
        policy=PolicySnapshot(),
    )
    assert repeated == first

    try:
        orchestrator.plan(
            mission.contract.mission_id,
            deficits=["contacts"],
            candidates=[
                ActionCandidate(
                    action_type=ActionType.REVIEW_CONFLICT,
                    deficit_code="contacts",
                )
            ],
            policy=PolicySnapshot(),
        )
    except ValueError as exc:
        assert str(exc) == "another plan is already pending for this turn"
    else:
        raise AssertionError("pending plan was replaced")


def test_money_is_non_negative_and_unbudgeted_actual_cost_blocks_mission():
    try:
        ActionCandidate(
            action_type=ActionType.QUERY_PROVIDER,
            estimated_cost_by_currency={"RUB": Decimal("-1")},
        )
    except ValidationError as exc:
        assert "money amounts must be non-negative" in str(exc)
    else:
        raise AssertionError("negative estimated cost was accepted")

    orchestrator = MissionOrchestrator()
    mission = create(orchestrator)
    plan = orchestrator.plan(
        mission.contract.mission_id,
        deficits=["identity"],
        candidates=[
            ActionCandidate(
                action_type=ActionType.QUERY_PROVIDER,
                target="unpriced provider",
            )
        ],
        policy=PolicySnapshot(),
    )
    result = orchestrator.record_turn(
        mission.contract.mission_id,
        plan=plan,
        outcome=ActionOutcome(
            state=ActionOutcomeState.SUCCEEDED,
            actual_cost_by_currency={"RUB": Decimal("1")},
        ),
        feedback=SufficiencyFeedback(
            question_states={"identity": QuestionState.PARTIALLY_VERIFIED},
            critical_gaps=["identity"],
        ),
    )

    assert result.lifecycle == MissionLifecycle.BLOCKED
    assert result.stop_reason == StopReason.BUDGET_EXHAUSTED


def test_two_turn_loop_preserves_artifacts_and_replans_on_critical_gap():
    orchestrator = MissionOrchestrator()
    mission = create(orchestrator)
    mission_id = mission.contract.mission_id
    policy = PolicySnapshot(
        allowed_hosts=frozenset({"example.test"}),
        remaining_actions=5,
    )

    first_plan = orchestrator.plan(
        mission_id,
        deficits=["identity", "contacts"],
        candidates=[
            ActionCandidate(
                action_type=ActionType.CRAWL_URL,
                target="https://example.test/about",
                deficit_code="identity",
                expected_sufficiency_gain=0.5,
            )
        ],
        policy=policy,
    )
    after_first = orchestrator.record_turn(
        mission_id,
        plan=first_plan,
        outcome=ActionOutcome(
            state=ActionOutcomeState.PARTIAL,
            artifact_refs=["doc_about"],
        ),
        feedback=SufficiencyFeedback(
            achieved=SufficiencyLevel.L1,
            question_states={
                "identity": QuestionState.PARTIALLY_VERIFIED,
            },
            critical_gaps=["identity", "contacts"],
        ),
    )

    second_plan = orchestrator.plan(
        mission_id,
        deficits=after_first.turns[-1].resulting_gaps,
        candidates=[
            ActionCandidate(
                action_type=ActionType.QUERY_PROVIDER,
                target="ИНН example",
                deficit_code="identity",
                expected_sufficiency_gain=0.7,
            )
        ],
        policy=policy,
    )
    after_second = orchestrator.record_turn(
        mission_id,
        plan=second_plan,
        outcome=ActionOutcome(
            state=ActionOutcomeState.SUCCEEDED,
            artifact_refs=["registry_hint"],
        ),
        feedback=SufficiencyFeedback(
            achieved=SufficiencyLevel.L2,
            question_states={"identity": QuestionState.VERIFIED},
            critical_gaps=["contacts", "workforce"],
        ),
    )

    assert after_first.lifecycle == MissionLifecycle.RUNNING
    assert after_second.lifecycle == MissionLifecycle.RUNNING
    assert [turn.turn_number for turn in after_second.turns] == [1, 2]
    assert after_second.turns[0].before_sufficiency == SufficiencyLevel.L0
    assert after_second.turns[1].before_sufficiency == SufficiencyLevel.L1
    assert after_second.artifact_refs == ["doc_about", "registry_hint"]
    assert after_second.question_states["identity"] == QuestionState.VERIFIED
    assert after_second.question_states["contacts"] == QuestionState.NOT_SEARCHED


def test_required_not_searched_question_blocks_false_completion():
    orchestrator = MissionOrchestrator()
    mission = create(orchestrator)
    mission_id = mission.contract.mission_id
    plan = orchestrator.plan(
        mission_id,
        deficits=["contacts"],
        candidates=[
            ActionCandidate(
                action_type=ActionType.STOP,
                deficit_code="claimed_complete",
            )
        ],
        policy=PolicySnapshot(remaining_actions=1),
    )
    feedback = SufficiencyFeedback(
        achieved=SufficiencyLevel.L4,
        question_states={
            "identity": QuestionState.VERIFIED,
            "contacts": QuestionState.NOT_SEARCHED,
        },
        critical_gaps=["contacts"],
        stop_reason=StopReason.SUFFICIENCY_REACHED,
    )

    result = orchestrator.record_turn(
        mission_id,
        plan=plan,
        outcome=ActionOutcome(state=ActionOutcomeState.SUCCEEDED),
        feedback=feedback,
    )

    assert result.lifecycle == MissionLifecycle.BLOCKED
    assert result.stop_reason == StopReason.INVALID_COMPLETION


def test_mission_state_never_leaks_to_another_analysis():
    orchestrator = MissionOrchestrator()
    first = create(orchestrator)
    second = create(orchestrator)
    plan = orchestrator.plan(
        first.contract.mission_id,
        deficits=["identity"],
        candidates=[
            ActionCandidate(
                action_type=ActionType.RESOLVE_IDENTITY,
                deficit_code="identity",
            )
        ],
        policy=PolicySnapshot(),
    )
    orchestrator.record_turn(
        first.contract.mission_id,
        plan=plan,
        outcome=ActionOutcome(
            state=ActionOutcomeState.PARTIAL,
            artifact_refs=["identity_candidate"],
        ),
        feedback=SufficiencyFeedback(
            question_states={"identity": QuestionState.PARTIALLY_VERIFIED},
            critical_gaps=["identity"],
        ),
    )

    untouched = orchestrator.get(second.contract.mission_id)

    assert untouched.turns == []
    assert untouched.artifact_refs == []
    assert untouched.question_states["identity"] == QuestionState.NOT_SEARCHED


def test_rest_mission_endpoint_returns_canonical_contract():
    request = default_site_mission_request("https://api.example/").model_dump(
        mode="json"
    )

    response = TestClient(app).post("/api/missions", json=request)

    assert response.status_code == 200
    payload = response.json()
    assert payload["contract"]["entry_point"] == "rest"
    assert payload["contract"]["target_sufficiency"] == "L4"
    assert payload["contract"]["contract_fingerprint"].startswith("sha256:")
    assert payload["lifecycle"] == "planned"
