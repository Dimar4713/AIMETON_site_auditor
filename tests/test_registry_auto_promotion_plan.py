from datetime import UTC, datetime

from app.entity_resolution.registry import (
    RegistryAuthority,
    RegistryEvidence,
)
from app.entity_resolution.registry_api import (
    RegistryVerificationRequest,
    _auto_promotion_plan,
)
from app.mission_orchestrator import (
    ActionCandidate,
    ActionOutcome,
    ActionOutcomeState,
    ActionType,
    EntryPoint,
    PolicySnapshot,
    QuestionState,
    SufficiencyFeedback,
    SufficiencyLevel,
    default_site_mission_request,
    get_mission_orchestrator,
    reset_mission_orchestrator,
)


def _record_turn(orchestrator, mission_id, plan, *, achieved):
    orchestrator.record_turn(
        mission_id,
        plan=plan,
        outcome=ActionOutcome(
            state=ActionOutcomeState.SUCCEEDED,
            artifact_refs=[f"artifact-turn-{plan.turn_number}"],
        ),
        feedback=SufficiencyFeedback(
            achieved=achieved,
            question_states={"identity": QuestionState.PARTIALLY_VERIFIED},
            critical_gaps=["official_registry_verification"],
        ),
    )


def test_registry_request_does_not_require_client_promotion_plan():
    request = RegistryVerificationRequest(
        base_result_id="identity_result_1",
        evidence=[
            RegistryEvidence(
                id="registry_evidence_1",
                authority=RegistryAuthority.FNS_EGRUL,
                source_url="https://egrul.nalog.ru/document/1",
                locator="json:$.rows[0]",
                accessed_at=datetime(2026, 7, 31, tzinfo=UTC),
                document_digest=f"sha256:{'a' * 64}",
                legal_name='ООО "Дедал"',
                inn="2400000009",
                ogrn="1022400000006",
            )
        ],
    )

    assert request.promotion_plan is None


def test_auto_registry_promotion_plan_is_third_mission_turn():
    reset_mission_orchestrator()
    orchestrator = get_mission_orchestrator()
    mission = orchestrator.create_mission(
        default_site_mission_request("https://example.test/"),
        entry_point=EntryPoint.REST,
    )
    crawl_plan = orchestrator.plan(
        mission.contract.mission_id,
        deficits=["identity"],
        candidates=[
            ActionCandidate(
                action_type=ActionType.CRAWL_URL,
                target="https://example.test/",
                deficit_code="bootstrap",
            )
        ],
        policy=PolicySnapshot(
            allowed_hosts=frozenset({"example.test"}),
            remaining_actions=10,
        ),
    )
    _record_turn(
        orchestrator,
        mission.contract.mission_id,
        crawl_plan,
        achieved=SufficiencyLevel.L1,
    )
    identity_plan = orchestrator.plan(
        mission.contract.mission_id,
        deficits=["identity"],
        candidates=[
            ActionCandidate(
                action_type=ActionType.RESOLVE_IDENTITY,
                target=mission.contract.mission_id,
                deficit_code="identity",
            )
        ],
        policy=PolicySnapshot(remaining_actions=9),
    )
    _record_turn(
        orchestrator,
        mission.contract.mission_id,
        identity_plan,
        achieved=SufficiencyLevel.L1,
    )
    evidence = RegistryEvidence(
        id="registry_evidence_1",
        authority=RegistryAuthority.FNS_EGRUL,
        source_url="https://egrul.nalog.ru/document/1",
        locator="json:$.rows[0]",
        accessed_at=datetime(2026, 7, 31, tzinfo=UTC),
        document_digest=f"sha256:{'b' * 64}",
        legal_name='ООО "Дедал"',
        inn="2400000009",
        ogrn="1022400000006",
    )

    plan = _auto_promotion_plan(mission.contract.mission_id, [evidence])

    assert plan.turn_number == 3
    assert plan.selected_action.action_type == ActionType.FETCH_DOCUMENT
    assert plan.selected_action.target == "https://egrul.nalog.ru/document/1"
    assert plan.selected_action.deficit_code == "official_registry_verification"
    selected_decision = next(
        decision
        for decision in plan.decisions
        if decision.candidate == plan.selected_action
    )
    assert selected_decision.admissible is True
    assert selected_decision.reason_codes == []
