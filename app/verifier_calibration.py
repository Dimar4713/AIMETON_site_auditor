from __future__ import annotations

from dataclasses import dataclass

from app.verifier_contract import VerificationRequest, VerificationResult


@dataclass(frozen=True)
class RankingCalibration:
    request_id: str
    comparable_pairs: int
    correct_pairwise_wins: int
    pairwise_accuracy: float
    correct_rank: int | None
    correct_is_top1: bool
    usable_measurement: bool


def evaluate_golden_fixture_ranking(
    request: VerificationRequest,
    result: VerificationResult,
) -> RankingCalibration:
    """Evaluate a verifier ranking against the synthetic Golden-5 P0 oracle.

    The P0 fixture oracle intentionally asserts only one strong ordering rule:
    the untouched `:correct` candidate must outrank every deliberately damaged
    variant.  It does not invent a total order among the different failure
    modes.  Blocked/degraded semantic results are recorded as unusable rather
    than silently counted as bad model quality.
    """
    correct_id = next(
        (candidate.id for candidate in request.candidates if candidate.payload.get("variant") == "correct"),
        None,
    )
    if correct_id is None:
        raise ValueError("request has no synthetic correct candidate")

    damaged_ids = [
        candidate.id
        for candidate in request.candidates
        if candidate.id != correct_id
    ]
    comparable_pairs = len(damaged_ids)

    if result.status != "measured":
        return RankingCalibration(
            request_id=request.request_id,
            comparable_pairs=comparable_pairs,
            correct_pairwise_wins=0,
            pairwise_accuracy=0.0,
            correct_rank=None,
            correct_is_top1=False,
            usable_measurement=False,
        )

    if set(result.ranking) != {candidate.id for candidate in request.candidates}:
        raise ValueError("measured result ranking must contain every candidate exactly once")

    positions = {candidate_id: index for index, candidate_id in enumerate(result.ranking)}
    correct_rank = positions[correct_id] + 1
    wins = sum(positions[correct_id] < positions[damaged_id] for damaged_id in damaged_ids)

    return RankingCalibration(
        request_id=request.request_id,
        comparable_pairs=comparable_pairs,
        correct_pairwise_wins=wins,
        pairwise_accuracy=wins / comparable_pairs if comparable_pairs else 1.0,
        correct_rank=correct_rank,
        correct_is_top1=correct_rank == 1,
        usable_measurement=True,
    )


def aggregate_calibration(rows: list[RankingCalibration]) -> dict[str, float | int]:
    usable = [row for row in rows if row.usable_measurement]
    total_pairs = sum(row.comparable_pairs for row in usable)
    total_wins = sum(row.correct_pairwise_wins for row in usable)
    return {
        "cases": len(rows),
        "usable_cases": len(usable),
        "measurement_coverage": len(usable) / len(rows) if rows else 0.0,
        "pairwise_accuracy": total_wins / total_pairs if total_pairs else 0.0,
        "top1_accuracy": (
            sum(row.correct_is_top1 for row in usable) / len(usable)
            if usable
            else 0.0
        ),
    }
