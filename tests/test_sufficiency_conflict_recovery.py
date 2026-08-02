from __future__ import annotations

from app.evidence_crawler.targeted_api import IdentityGuardState
from app.mission_orchestrator import ActionType, SufficiencyLevel
from app.sufficiency_evaluator.service import evaluate_targeted_crawl
from tests.test_sufficiency_evaluator import _fixture


def test_identity_conflict_returns_mission_to_targeted_crawl():
    orchestrator, mission, envelope = _fixture(IdentityGuardState.CONFLICTING)

    result = evaluate_targeted_crawl(
        orchestrator,
        mission.contract.mission_id,
        envelope,
    )

    assert result.achieved_level == SufficiencyLevel.L0
    assert result.report_release_allowed is False
    assert "identity_conflict" in result.critical_gaps
    assert result.next_plan is not None
    assert result.next_plan.selected_action.action_type == ActionType.CRAWL_URL
    assert result.next_plan.selected_action.target == str(mission.contract.target_url)
    assert result.next_plan.selected_action.deficit_code == "identity_conflict"
    assert result.turn_record is not None
    assert result.turn_record.next_action_type == ActionType.CRAWL_URL.value
    assert result.turn_record.next_action_deficit == "identity_conflict"
