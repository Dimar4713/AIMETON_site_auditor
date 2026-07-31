from app.evidence_crawler.api import BootstrapRunRequest, _bootstrap_plan
from app.mission_orchestrator import (
    ActionType,
    EntryPoint,
    default_site_mission_request,
    get_mission_orchestrator,
    reset_mission_orchestrator,
)


def setup_function() -> None:
    reset_mission_orchestrator()


def test_bootstrap_request_keeps_explicit_plan_optional() -> None:
    request = BootstrapRunRequest()

    assert request.plan is None
    assert request.policy.max_pages == 8


def test_api_builds_bootstrap_plan_from_canonical_mission() -> None:
    orchestrator = get_mission_orchestrator()
    mission = orchestrator.create_mission(
        default_site_mission_request("https://example.test/"),
        entry_point=EntryPoint.REST,
    )

    plan = _bootstrap_plan(mission.contract.mission_id)

    assert plan.mission_id == mission.contract.mission_id
    assert plan.turn_number == 1
    assert plan.selected_action.action_type == ActionType.CRAWL_URL
    assert plan.selected_action.target == "https://example.test/"
    assert plan.selected_action.deficit_code == "bootstrap"
    assert set(plan.input_deficits) == set(mission.question_states)


def test_api_bootstrap_plan_is_issued_once_per_turn() -> None:
    orchestrator = get_mission_orchestrator()
    mission = orchestrator.create_mission(
        default_site_mission_request("https://example.test/"),
        entry_point=EntryPoint.REST,
    )

    first = _bootstrap_plan(mission.contract.mission_id)
    repeated = _bootstrap_plan(mission.contract.mission_id)

    assert repeated == first
