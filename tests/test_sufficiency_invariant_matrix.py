from __future__ import annotations

import pytest

from app.mission_orchestrator import SufficiencyLevel
from app.sufficiency_evaluator.models import (
    DimensionAssessment,
    SufficiencyDimension,
)
from app.sufficiency_evaluator.service import _minimum


ALL_LEVELS = [
    SufficiencyLevel.L0,
    SufficiencyLevel.L1,
    SufficiencyLevel.L2,
    SufficiencyLevel.L3,
    SufficiencyLevel.L4,
    SufficiencyLevel.L5,
]

ALL_DIMENSIONS = {
    SufficiencyDimension.COVERAGE,
    SufficiencyDimension.EVIDENCE_QUALITY,
    SufficiencyDimension.IDENTITY_RESOLUTION,
    SufficiencyDimension.SOURCE_RELIABILITY,
    SufficiencyDimension.FRESHNESS,
    SufficiencyDimension.CONSISTENCY,
    SufficiencyDimension.EXECUTION_INTEGRITY,
}


def test_canonical_scale_contains_exactly_l0_through_l5_in_order():
    assert list(SufficiencyLevel) == ALL_LEVELS


def test_canonical_dimension_set_contains_exactly_seven_invariants():
    assert set(SufficiencyDimension) == ALL_DIMENSIONS
    assert len(ALL_DIMENSIONS) == 7


@pytest.mark.parametrize("weakest", ALL_LEVELS)
def test_weakest_link_rule_holds_for_every_level(weakest: SufficiencyLevel):
    levels = [SufficiencyLevel.L5] * len(ALL_DIMENSIONS)
    levels[3] = weakest

    assessments = [
        DimensionAssessment(dimension=dimension, level=level)
        for dimension, level in zip(sorted(ALL_DIMENSIONS, key=str), levels, strict=True)
    ]

    assert _minimum([item.level for item in assessments]) == weakest


@pytest.mark.parametrize("dimension", sorted(ALL_DIMENSIONS, key=str))
def test_each_dimension_can_independently_limit_the_result(
    dimension: SufficiencyDimension,
):
    assessments = [
        DimensionAssessment(
            dimension=current,
            level=(SufficiencyLevel.L2 if current == dimension else SufficiencyLevel.L5),
        )
        for current in sorted(ALL_DIMENSIONS, key=str)
    ]

    assert _minimum([item.level for item in assessments]) == SufficiencyLevel.L2
