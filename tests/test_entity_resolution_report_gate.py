from __future__ import annotations

import pytest

from app.entity_resolution import IdentityResolutionState, ProvisionalEntityResolver
from app.mission_orchestrator import ActionType, MissionOrchestrator
from app.sef.report import (
    ReportReleaseError,
    build_human_reviewed_report,
    build_review_package_from_request,
)
from tests.test_entity_resolution import (
    _batch,
    _crawl_plan,
    _record_crawl_and_plan_resolution,
)
from tests.test_sef_report_v1 import _release_control, _report_request, _source_request


def test_identity_unresolved_emits_explicit_search_deficit():
    orchestrator = MissionOrchestrator()
    resolver = ProvisionalEntityResolver()
    mission, crawl_plan = _crawl_plan(orchestrator)
    batch = _batch(
        mission,
        crawl_plan,
        inn="2400000000",
        ogrn="1022400000000",
    )
    resolution_plan = _record_crawl_and_plan_resolution(
        orchestrator,
        mission,
        crawl_plan,
    )

    result = resolver.resolve(
        orchestrator,
        mission.contract.mission_id,
        plan=resolution_plan,
        bootstrap_results=[batch],
    )

    assert result.state == IdentityResolutionState.UNRESOLVED
    assert "identity_unresolved" in result.gaps
    assert result.recommended_feedback.critical_gaps
    assert "identity_unresolved" in result.recommended_feedback.critical_gaps
    assert result.selected_candidate_id is None
    assert any(
        candidate.action_type in {ActionType.QUERY_PROVIDER, ActionType.FETCH_DOCUMENT}
        for candidate in result.next_action_candidates
    )


def test_identity_unresolved_physically_blocks_client_report_release():
    control = _release_control(
        identity_state="unresolved",
        reason_codes=["identity_unresolved"],
    )
    source = _source_request(release_control=control)

    package = build_review_package_from_request(source)

    assert package.reviewable is False
    assert "identity_unresolved" in package.blockers

    with pytest.raises(ReportReleaseError) as error:
        build_human_reviewed_report(_report_request(source=source))

    assert "identity_unresolved" in error.value.blockers
