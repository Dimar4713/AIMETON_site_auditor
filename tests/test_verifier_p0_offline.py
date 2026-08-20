from pathlib import Path
import unittest

from pydantic import ValidationError

from app.verifier_contract import (
    CandidateVerificationScore,
    VerificationRequest,
    VerificationResult,
)
from app.verifier_fixtures import CANDIDATE_CLASSES, build_sef_verification_requests


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "sef" / "benchmark-20-v0.1.json"
GOLDEN = ROOT / "benchmarks" / "sef" / "golden-5-v0.1.json"


class VerifierP0OfflineContractTest(unittest.TestCase):
    def test_golden_5_builds_five_deterministic_candidate_classes_per_case(self):
        requests = build_sef_verification_requests(BENCHMARK, GOLDEN)
        self.assertEqual(len(requests), 5)

        for request in requests:
            self.assertIsInstance(request, VerificationRequest)
            self.assertFalse(request.client_release_authority)
            self.assertEqual(len(request.candidates), 5)
            self.assertEqual(
                [candidate.payload["variant"] for candidate in request.candidates],
                list(CANDIDATE_CLASSES),
            )
            self.assertEqual(len({candidate.id for candidate in request.candidates}), 5)
            self.assertEqual(len(request.criteria), 4)

    def test_candidate_variants_expose_expected_failure_modes(self):
        request = build_sef_verification_requests(BENCHMARK, GOLDEN)[0]
        by_variant = {candidate.payload["variant"]: candidate.payload for candidate in request.candidates}

        self.assertEqual(by_variant["correct"]["identity_status"], "resolved")
        self.assertLess(
            len(by_variant["incomplete"]["facts"]),
            len(by_variant["correct"]["facts"]),
        )
        self.assertTrue(
            any(fact.get("verification_status") == "unsupported" for fact in by_variant["unsupported"]["facts"])
        )
        self.assertEqual(by_variant["identity_conflicted"]["identity_status"], "conflicted")
        self.assertTrue(all(fact.get("source") is None for fact in by_variant["evidence_poor"]["facts"]))

    def test_semantic_verifier_result_cannot_grant_release_or_override_hard_gates(self):
        result = VerificationResult(
            request_id="request-1",
            status="measured",
            reason_code="measured",
            ranking=["candidate-a", "candidate-b"],
            scores=[
                CandidateVerificationScore(
                    candidate_id="candidate-a",
                    score=0.8,
                    criterion_scores={"factual_correctness": 0.9},
                    signal_status="valid",
                )
            ],
            verifier_engine="test-engine",
            verifier_revision="deadbeef",
            input_digest="digest",
        )
        self.assertFalse(result.client_release_eligible)
        self.assertFalse(result.hard_gate_override)

        with self.assertRaises(ValidationError):
            VerificationResult(
                request_id="request-1",
                status="measured",
                reason_code="measured",
                verifier_engine="test-engine",
                verifier_revision="deadbeef",
                input_digest="digest",
                client_release_eligible=True,
            )

        with self.assertRaises(ValidationError):
            VerificationResult(
                request_id="request-1",
                status="measured",
                reason_code="measured",
                verifier_engine="test-engine",
                verifier_revision="deadbeef",
                input_digest="digest",
                hard_gate_override=True,
            )


if __name__ == "__main__":
    unittest.main()
