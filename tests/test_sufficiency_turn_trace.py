from app.mission_orchestrator import ActionType, SufficiencyLevel
from app.sufficiency_evaluator.service import evaluate_targeted_crawl
from app.sufficiency_evaluator.trace_store import (
    get_sufficiency_trace_store,
    reset_sufficiency_trace_store,
)
from tests.test_sufficiency_evaluator import _fixture


def setup_function() -> None:
    reset_sufficiency_trace_store()


def test_evaluation_persists_before_after_evidence_and_next_action_reason():
    orchestrator, mission, envelope = _fixture()

    result = evaluate_targeted_crawl(
        orchestrator,
        mission.contract.mission_id,
        envelope,
    )

    records = get_sufficiency_trace_store().list_for_mission(
        mission.contract.mission_id
    )
    assert len(records) == 1
    record = records[0]
    assert result.turn_record == record
    assert record.before_level == SufficiencyLevel.L1
    assert record.after_level == SufficiencyLevel.L4
    assert record.next_action_type == ActionType.STOP.value
    assert record.next_action_deficit == "sufficiency_reached"
    assert record.next_action_reason == "highest_admissible_expected_gain"
    assert "document_root" in record.evidence_refs
    assert "https://example.test/requisites.pdf" in record.evidence_refs
    assert record.analysis_id == mission.contract.analysis_id
    assert record.correlation_id == mission.contract.correlation_id


def test_identity_conflict_trace_keeps_gap_and_targeted_recovery_decision():
    from app.evidence_crawler.targeted_api import IdentityGuardState

    orchestrator, mission, envelope = _fixture(IdentityGuardState.CONFLICTING)

    result = evaluate_targeted_crawl(
        orchestrator,
        mission.contract.mission_id,
        envelope,
    )

    record = get_sufficiency_trace_store().latest(mission.contract.mission_id)
    assert record is not None
    assert result.turn_record == record
    assert record.before_level == SufficiencyLevel.L1
    assert record.after_level == SufficiencyLevel.L0
    assert "identity_conflict" in record.critical_gaps
    assert record.next_action_type == ActionType.CRAWL_URL.value
    assert record.next_action_deficit == "identity_conflict"
