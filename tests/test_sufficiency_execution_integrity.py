from __future__ import annotations

"""Regression coverage for crawler execution-integrity projection."""

import pytest

from app.evidence_crawler.models import CrawlStatus
from app.mission_orchestrator import SufficiencyLevel
from app.sufficiency_evaluator.models import SufficiencyDimension
from app.sufficiency_evaluator.service import evaluate_targeted_crawl
from tests.test_sufficiency_evaluator import _fixture


@pytest.mark.parametrize(
    ("status", "expected_level", "expected_gap"),
    [
        (CrawlStatus.DEGRADED, SufficiencyLevel.L2, "execution_degraded"),
        (CrawlStatus.BLOCKED, SufficiencyLevel.L0, "critical_source_blocked"),
    ],
)
def test_crawler_failure_is_visible_in_execution_integrity(
    status: CrawlStatus,
    expected_level: SufficiencyLevel,
    expected_gap: str,
):
    orchestrator, mission, envelope = _fixture()
    failed_crawl = envelope.crawl.model_copy(update={"status": status})
    failed_envelope = envelope.model_copy(update={"crawl": failed_crawl})

    result = evaluate_targeted_crawl(
        orchestrator,
        mission.contract.mission_id,
        failed_envelope,
    )

    execution_integrity = next(
        item
        for item in result.dimensions
        if item.dimension == SufficiencyDimension.EXECUTION_INTEGRITY
    )
    assert execution_integrity.level == expected_level
    assert expected_gap in result.critical_gaps
    assert result.report_release_allowed is False
