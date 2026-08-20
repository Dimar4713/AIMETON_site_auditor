from pathlib import Path
import unittest

from app.verifier_calibration import aggregate_calibration, evaluate_golden_fixture_ranking
from app.verifier_contract import VerificationResult
from app.verifier_fixtures import build_sef_verification_requests


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "sef" / "benchmark-20-v0.1.json"
GOLDEN = ROOT / "benchmarks" / "sef" / "golden-5-v0.1.json"


def measured_result(request, ranking):
    return VerificationResult(
        request_id=request.request_id,
        status="measured",
        reason_code="measured",
        ranking=ranking,
        verifier_engine="offline-test",
        verifier_revision="0" * 40,
        input_digest="digest",
    )


class VerifierCalibrationTest(unittest.TestCase):
    def setUp(self):
        self.requests = build_sef_verification_requests(BENCHMARK, GOLDEN)

    def test_correct_top1_scores_perfectly_without_ordering_failure_modes(self):
        request = self.requests[0]
        ranking = [candidate.id for candidate in request.candidates]
        row = evaluate_golden_fixture_ranking(request, measured_result(request, ranking))
        self.assertTrue(row.usable_measurement)
        self.assertTrue(row.correct_is_top1)
        self.assertEqual(row.correct_rank, 1)
        self.assertEqual(row.comparable_pairs, 4)
        self.assertEqual(row.correct_pairwise_wins, 4)
        self.assertEqual(row.pairwise_accuracy, 1.0)

    def test_correct_middle_rank_counts_only_observable_pairwise_wins(self):
        request = self.requests[0]
        ids = [candidate.id for candidate in request.candidates]
        ranking = [ids[1], ids[2], ids[0], ids[3], ids[4]]
        row = evaluate_golden_fixture_ranking(request, measured_result(request, ranking))
        self.assertEqual(row.correct_rank, 3)
        self.assertEqual(row.correct_pairwise_wins, 2)
        self.assertEqual(row.pairwise_accuracy, 0.5)
        self.assertFalse(row.correct_is_top1)

    def test_blocked_result_reduces_measurement_coverage_instead_of_becoming_fake_score(self):
        request = self.requests[0]
        blocked = VerificationResult(
            request_id=request.request_id,
            status="blocked",
            reason_code="missing_score_evidence",
            verifier_engine="offline-test",
            verifier_revision="0" * 40,
            input_digest="digest",
        )
        row = evaluate_golden_fixture_ranking(request, blocked)
        self.assertFalse(row.usable_measurement)
        self.assertIsNone(row.correct_rank)

        perfect_rows = []
        for item in self.requests[1:]:
            ranking = [candidate.id for candidate in item.candidates]
            perfect_rows.append(evaluate_golden_fixture_ranking(item, measured_result(item, ranking)))
        metrics = aggregate_calibration([row, *perfect_rows])
        self.assertEqual(metrics["cases"], 5)
        self.assertEqual(metrics["usable_cases"], 4)
        self.assertEqual(metrics["measurement_coverage"], 0.8)
        self.assertEqual(metrics["pairwise_accuracy"], 1.0)
        self.assertEqual(metrics["top1_accuracy"], 1.0)

    def test_measured_result_with_malformed_ranking_is_rejected(self):
        request = self.requests[0]
        ids = [candidate.id for candidate in request.candidates]
        result = measured_result(request, [ids[0], ids[1], ids[1], ids[3], ids[4]])
        with self.assertRaises(ValueError):
            evaluate_golden_fixture_ranking(request, result)


if __name__ == "__main__":
    unittest.main()
