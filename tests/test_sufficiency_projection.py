from app.evidence_crawler.targeted_api import IdentityGuardState
from app.mission_orchestrator import SufficiencyLevel
from app.sufficiency_evaluator.projection import ResultUsage, project_sufficiency
from app.sufficiency_evaluator.service import evaluate_targeted_crawl
from tests.test_sufficiency_evaluator import _fixture


def test_projection_exposes_target_achieved_reasons_and_internal_only_usage():
    orchestrator, mission, envelope = _fixture(IdentityGuardState.CONFLICTING)
    evaluation = evaluate_targeted_crawl(
        orchestrator,
        mission.contract.mission_id,
        envelope,
    )

    projection = project_sufficiency(evaluation)

    assert projection.target_level == SufficiencyLevel.L4
    assert projection.achieved_level == SufficiencyLevel.L0
    assert "identity_conflict" in projection.reason_codes
    assert projection.allowed_usage == ResultUsage.INTERNAL_ONLY
    assert projection.report_release_allowed is False


def test_projection_allows_client_report_only_for_releaseable_evaluation():
    orchestrator, mission, envelope = _fixture()
    evaluation = evaluate_targeted_crawl(
        orchestrator,
        mission.contract.mission_id,
        envelope,
    )

    projection = project_sufficiency(evaluation)

    assert projection.target_level == SufficiencyLevel.L4
    assert projection.achieved_level == SufficiencyLevel.L4
    assert projection.reason_codes == []
    assert projection.allowed_usage == ResultUsage.CLIENT_REPORT
    assert projection.report_release_allowed is True
