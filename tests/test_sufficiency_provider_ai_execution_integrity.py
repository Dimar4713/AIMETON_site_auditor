from __future__ import annotations

import pytest

from app.mission_orchestrator import SufficiencyLevel
from app.sufficiency_evaluator.execution_integrity import project_execution_failures
from app.sufficiency_evaluator.models import ExecutionFailureKind, SufficiencyDimension
from app.sufficiency_evaluator.service import evaluate_targeted_crawl
from tests.test_sufficiency_evaluator import _fixture


@pytest.mark.parametrize(
    "failure",
    [ExecutionFailureKind.PROVIDER, ExecutionFailureKind.AI],
)
def test_provider_and_ai_failures_are_visible_and_block_release(
    failure: ExecutionFailureKind,
):
    orchestrator, mission, envelope = _fixture()
    baseline = evaluate_targeted_crawl(
        orchestrator,
        mission.contract.mission_id,
        envelope,
    )
    assert baseline.report_release_allowed is True

    result = project_execution_failures(baseline, {failure})
    execution_integrity = next(
        item
        for item in result.dimensions
        if item.dimension == SufficiencyDimension.EXECUTION_INTEGRITY
    )

    assert execution_integrity.level == SufficiencyLevel.L0
    assert execution_integrity.reason_codes == [failure.value]
    assert failure.value in result.critical_gaps
    assert result.achieved_level == SufficiencyLevel.L0
    assert result.delta.after == SufficiencyLevel.L0
    assert result.report_release_allowed is False
    assert result.stop_reason is None
    assert result.turn_record is not None
    assert result.turn_record.after_level == SufficiencyLevel.L0
    assert failure.value in result.turn_record.critical_gaps


def test_multiple_execution_failures_are_deterministic_and_deduplicated():
    orchestrator, mission, envelope = _fixture()
    baseline = evaluate_targeted_crawl(
        orchestrator,
        mission.contract.mission_id,
        envelope,
    )

    result = project_execution_failures(
        baseline,
        {ExecutionFailureKind.AI, ExecutionFailureKind.PROVIDER},
    )
    execution_integrity = next(
        item
        for item in result.dimensions
        if item.dimension == SufficiencyDimension.EXECUTION_INTEGRITY
    )

    assert execution_integrity.reason_codes == ["ai_failure", "provider_failure"]
    assert result.critical_gaps.count("ai_failure") == 1
    assert result.critical_gaps.count("provider_failure") == 1
