from __future__ import annotations

from app.mission_orchestrator import SufficiencyLevel
from app.sufficiency_evaluator.models import (
    ExecutionFailureKind,
    SufficiencyDimension,
    SufficiencyEvaluation,
)


def project_execution_failures(
    evaluation: SufficiencyEvaluation,
    failures: set[ExecutionFailureKind] | None = None,
) -> SufficiencyEvaluation:
    """Project typed provider/AI failures into the existing fail-closed UDP result."""
    failures = failures or set()
    if not failures:
        return evaluation

    reason_codes = sorted(item.value for item in failures)
    dimensions = [
        item.model_copy(
            update={"level": SufficiencyLevel.L0, "reason_codes": reason_codes}
        )
        if item.dimension == SufficiencyDimension.EXECUTION_INTEGRITY
        else item
        for item in evaluation.dimensions
    ]
    critical_gaps = list(dict.fromkeys([*evaluation.critical_gaps, *reason_codes]))
    delta = evaluation.delta.model_copy(
        update={"after": SufficiencyLevel.L0, "critical_gaps": critical_gaps}
    )
    turn_record = (
        evaluation.turn_record.model_copy(
            update={"after_level": SufficiencyLevel.L0, "critical_gaps": critical_gaps}
        )
        if evaluation.turn_record is not None
        else None
    )
    return evaluation.model_copy(
        update={
            "achieved_level": SufficiencyLevel.L0,
            "dimensions": dimensions,
            "critical_gaps": critical_gaps,
            "delta": delta,
            "report_release_allowed": False,
            "stop_reason": None,
            "turn_record": turn_record,
        }
    )
