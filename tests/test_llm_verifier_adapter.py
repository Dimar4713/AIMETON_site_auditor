from pathlib import Path
import unittest

from app.llm_verifier_adapter import (
    LLM_VERIFIER_PINNED_SHA,
    LLMVerifierSelectionEnvelope,
    adapt_llm_verifier_selection,
)
from app.verifier_fixtures import build_sef_verification_requests


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "sef" / "benchmark-20-v0.1.json"
GOLDEN = ROOT / "benchmarks" / "sef" / "golden-5-v0.1.json"


class LLMVerifierAdapterTest(unittest.TestCase):
    def setUp(self):
        self.request = build_sef_verification_requests(BENCHMARK, GOLDEN)[0]

    def test_valid_pinned_selection_maps_to_advisory_result(self):
        envelope = LLMVerifierSelectionEnvelope(
            engine_revision=LLM_VERIFIER_PINNED_SHA,
            ranking_indices=[0, 1, 4, 3, 2],
            scores=[0.9, 0.7, 0.2, 0.3, 0.4],
            signal_status="valid",
        )
        result = adapt_llm_verifier_selection(self.request, envelope)
        self.assertEqual(result.status, "measured")
        self.assertEqual(result.reason_code, "measured")
        self.assertEqual(result.ranking[0], f"{self.request.metadata['case_id']}:correct")
        self.assertFalse(result.client_release_eligible)
        self.assertFalse(result.hard_gate_override)
        self.assertEqual(result.verifier_revision, LLM_VERIFIER_PINNED_SHA)

    def test_revision_drift_fails_closed(self):
        envelope = LLMVerifierSelectionEnvelope(
            engine_revision="0" * 40,
            ranking_indices=[0, 1, 2, 3, 4],
            scores=[0.9, 0.7, 0.5, 0.3, 0.1],
            signal_status="valid",
        )
        result = adapt_llm_verifier_selection(self.request, envelope)
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason_code, "adapter_failure")
        self.assertTrue(result.metadata["revision_mismatch"])

    def test_missing_score_signal_fails_closed(self):
        envelope = LLMVerifierSelectionEnvelope(
            engine_revision=LLM_VERIFIER_PINNED_SHA,
            ranking_indices=[0, 1, 2, 3, 4],
            scores=[0.5] * 5,
            signal_status="missing",
        )
        result = adapt_llm_verifier_selection(self.request, envelope)
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason_code, "missing_score_evidence")

    def test_malformed_ranking_fails_closed(self):
        envelope = LLMVerifierSelectionEnvelope(
            engine_revision=LLM_VERIFIER_PINNED_SHA,
            ranking_indices=[0, 1, 1, 3, 4],
            scores=[0.9, 0.7, 0.5, 0.3, 0.1],
            signal_status="valid",
        )
        result = adapt_llm_verifier_selection(self.request, envelope)
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason_code, "adapter_failure")


if __name__ == "__main__":
    unittest.main()
