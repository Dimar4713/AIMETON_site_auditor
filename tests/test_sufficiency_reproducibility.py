from __future__ import annotations

from app.mission_orchestrator import ActionType
from app.sufficiency_evaluator.service import evaluate_targeted_crawl
from app.sufficiency_evaluator.trace_store import reset_sufficiency_trace_store
from tests.test_sufficiency_evaluator import _fixture


def _stable_projection(result) -> dict:
    selected = result.next_plan.selected_action
    action_target = (
        "<mission>"
        if selected.action_type == ActionType.STOP
        else selected.target
    )
    return {
        "target_level": result.target_level,
        "achieved_level": result.achieved_level,
        "dimensions": [
            (item.dimension, item.level, tuple(item.reason_codes))
            for item in result.dimensions
        ],
        "question_states": sorted(result.question_states.items()),
        "critical_gaps": tuple(result.critical_gaps),
        "delta": {
            "before": result.delta.before,
            "after": result.delta.after,
            "improved_dimensions": tuple(result.delta.improved_dimensions),
            "critical_gaps": tuple(result.delta.critical_gaps),
        },
        "report_release_allowed": result.report_release_allowed,
        "stop_reason": result.stop_reason,
        "next_action": (
            selected.action_type,
            action_target,
            selected.deficit_code,
            selected.expected_sufficiency_gain,
        ),
        "selection_reason": result.next_plan.selection_reason,
    }


def test_identical_evidence_snapshot_produces_reproducible_sufficiency_evaluation():
    reset_sufficiency_trace_store()
    first_orchestrator, first_mission, first_envelope = _fixture()
    first = evaluate_targeted_crawl(
        first_orchestrator,
        first_mission.contract.mission_id,
        first_envelope,
    )

    reset_sufficiency_trace_store()
    second_orchestrator, second_mission, second_envelope = _fixture()
    second = evaluate_targeted_crawl(
        second_orchestrator,
        second_mission.contract.mission_id,
        second_envelope,
    )

    assert _stable_projection(first) == _stable_projection(second)
