from datetime import UTC, datetime

from app.document_pipeline.models import FetchPath
from app.evidence_crawler.models import (
    BootstrapCrawlResult,
    CrawledPage,
    CrawlStatus,
    PageType,
    PrimaryDocumentCandidate,
    RobotsState,
)
from app.evidence_crawler.targeted_api import (
    IdentityGuardState,
    TargetedCrawlEnvelope,
)
from app.mission_orchestrator import (
    ActionCandidate,
    ActionOutcome,
    ActionOutcomeState,
    ActionType,
    EntryPoint,
    MissionBudget,
    MissionCreateRequest,
    MissionOrchestrator,
    MissionQuestion,
    PolicySnapshot,
    QuestionState,
    SufficiencyFeedback,
    SufficiencyLevel,
)
from app.sufficiency_evaluator.service import evaluate_targeted_crawl


DIGEST = f"sha256:{'a' * 64}"


def _fixture(guard_state=IdentityGuardState.ALIGNED):
    orchestrator = MissionOrchestrator()
    mission = orchestrator.create_mission(
        MissionCreateRequest(
            target_url="https://example.test/",
            goal="Verify identity",
            target_sufficiency=SufficiencyLevel.L4,
            questions=[MissionQuestion(code="identity")],
            budget=MissionBudget(max_actions=5),
        ),
        entry_point=EntryPoint.REST,
    )
    plan = orchestrator.plan(
        mission.contract.mission_id,
        deficits=["targeted_company_profile"],
        candidates=[
            ActionCandidate(
                action_type=ActionType.CRAWL_URL,
                target="https://example.test/",
                deficit_code="targeted_company_profile",
            )
        ],
        policy=PolicySnapshot(
            allowed_hosts=frozenset({"example.test"}),
            remaining_actions=5,
        ),
    )
    outcome = ActionOutcome(
        state=ActionOutcomeState.SUCCEEDED,
        artifact_refs=["document_root"],
    )
    orchestrator.record_turn(
        mission.contract.mission_id,
        plan=plan,
        outcome=outcome,
        feedback=SufficiencyFeedback(
            achieved=SufficiencyLevel.L1,
            question_states={"identity": QuestionState.PARTIALLY_VERIFIED},
            critical_gaps=["identity"],
        ),
    )
    page = CrawledPage(
        requested_url="https://example.test/",
        final_url="https://example.test/",
        depth=0,
        page_type=PageType.ROOT,
        document_id="document_root",
        title="Example",
        accessed_at=datetime(2026, 7, 31, tzinfo=UTC),
        media_type="text/html",
        fetch_path=FetchPath.STATIC,
        raw_content_digest=DIGEST,
        normalized_content_digest=DIGEST,
        link_count=1,
    )
    crawl = BootstrapCrawlResult(
        status=CrawlStatus.COMPLETED,
        mission_id=mission.contract.mission_id,
        analysis_id=mission.contract.analysis_id,
        correlation_id=mission.contract.correlation_id,
        root_url="https://example.test/",
        plan=plan,
        robots_state=RobotsState.ALLOWED,
        pages=[page],
        primary_document_candidates=[
            PrimaryDocumentCandidate(
                url="https://example.test/requisites.pdf",
                media_type="application/pdf",
                source_document_id="document_root",
                source_locator="css:a",
                same_domain=True,
            )
        ],
        outcome=outcome,
    )
    envelope = TargetedCrawlEnvelope(
        identity_result_id="identity_result_1",
        selected_candidate_id="candidate_1",
        guard_state=guard_state,
        expected_identifiers={"inn": ["2400000009"]},
        observed_identifiers={"inn": ["2400000009"]},
        crawl=crawl,
    )
    return orchestrator, mission, envelope


def test_weakest_link_allows_report_only_at_l4_without_critical_gaps():
    orchestrator, mission, envelope = _fixture()
    result = evaluate_targeted_crawl(
        orchestrator,
        mission.contract.mission_id,
        envelope,
    )
    assert result.achieved_level == SufficiencyLevel.L4
    assert result.report_release_allowed is True
    assert result.critical_gaps == []
    assert result.next_plan.selected_action.action_type == ActionType.STOP


def test_identity_conflict_forces_l0_and_targeted_recovery():
    orchestrator, mission, envelope = _fixture(IdentityGuardState.CONFLICTING)
    result = evaluate_targeted_crawl(
        orchestrator,
        mission.contract.mission_id,
        envelope,
    )
    assert result.achieved_level == SufficiencyLevel.L0
    assert result.report_release_allowed is False
    assert "identity_conflict" in result.critical_gaps
    assert result.next_plan.selected_action.action_type == ActionType.CRAWL_URL
    assert result.next_plan.selected_action.target == str(mission.contract.target_url)
    assert result.next_plan.selected_action.deficit_code == "identity_conflict"
