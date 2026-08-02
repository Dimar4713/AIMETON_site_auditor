from __future__ import annotations

from app.mission_orchestrator import (
    ActionCandidate,
    ActionType,
    EntryPoint,
    MissionOrchestrator,
    PolicySnapshot,
    default_site_mission_request,
)


def _mission() -> tuple[MissionOrchestrator, str]:
    orchestrator = MissionOrchestrator()
    snapshot = orchestrator.create_mission(
        default_site_mission_request("https://example.test"),
        entry_point=EntryPoint.REST,
    )
    return orchestrator, snapshot.contract.mission_id


def test_provider_without_active_deficit_is_not_selected():
    orchestrator, mission_id = _mission()
    active = ActionCandidate(
        action_type=ActionType.QUERY_PROVIDER,
        target="registry-provider",
        deficit_code="financials",
        expected_sufficiency_gain=0.4,
        ai_priority=0.8,
    )
    unrelated = ActionCandidate(
        action_type=ActionType.QUERY_PROVIDER,
        target="ownership-provider",
        deficit_code="ownership",
        expected_sufficiency_gain=0.9,
        ai_priority=1.0,
    )

    plan = orchestrator.plan(
        mission_id,
        deficits=["financials"],
        candidates=[active, unrelated],
        policy=PolicySnapshot(remaining_actions=5),
    )

    assert plan.selected_action == active
    unrelated_decision = next(
        item for item in plan.decisions if item.candidate == unrelated
    )
    assert unrelated_decision.admissible is False
    assert "deficit_not_active" in unrelated_decision.reason_codes


def test_no_active_provider_deficit_results_in_fail_closed_stop():
    orchestrator, mission_id = _mission()
    provider = ActionCandidate(
        action_type=ActionType.QUERY_PROVIDER,
        target="registry-provider",
        deficit_code="financials",
        expected_sufficiency_gain=0.8,
        ai_priority=1.0,
    )

    plan = orchestrator.plan(
        mission_id,
        deficits=["identity"],
        candidates=[provider],
        policy=PolicySnapshot(remaining_actions=5),
    )

    assert plan.selected_action.action_type == ActionType.STOP
    assert plan.selection_reason == "policy_no_admissible_action"
    assert plan.decisions[0].admissible is False
    assert "deficit_not_active" in plan.decisions[0].reason_codes
