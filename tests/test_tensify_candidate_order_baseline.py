import json
import unittest
from pathlib import Path

from k_safeguard.providers.tensify import (
    DEFAULT_TENSIFY_DIVERSIFY_FROM,
    TENSIFY_CANDIDATE_VERSION,
    TensifyInverseProvider,
)


BASELINE = (
    Path(__file__).resolve().parents[1]
    / "experiments"
    / "benchmark"
    / "baselines"
    / "tensify_candidate_order_v1.json"
)


class TensifyCandidateOrderBaselineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = json.loads(BASELINE.read_text(encoding="utf-8"))

    def test_full_restoration_remains_first(self) -> None:
        example = self.result["long_input_example"]
        self.assertEqual(example["legacy_replacement_counts"][0], 17)
        self.assertEqual(example["diverse_replacement_counts"][0], 17)

    def test_long_input_uses_multiple_replacement_tiers(self) -> None:
        example = self.result["long_input_example"]
        self.assertEqual(len(set(example["legacy_replacement_counts"])), 2)
        self.assertEqual(len(set(example["diverse_replacement_counts"])), 9)

    def test_repository_default_reproduces_recorded_long_input_order(self) -> None:
        policy = self.result["diverse_long_input"]
        proposals = list(TensifyInverseProvider().generate("까" * 17))
        replacement_counts = [
            int(dict(proposal.metadata)["replacement_count"])
            for proposal in proposals
        ]

        self.assertEqual(
            TENSIFY_CANDIDATE_VERSION,
            policy["candidate_generator_version"],
        )
        self.assertEqual(DEFAULT_TENSIFY_DIVERSIFY_FROM, policy["diversify_from"])
        self.assertEqual(
            replacement_counts,
            self.result["long_input_example"]["diverse_replacement_counts"],
        )

    def test_guardrail_counts_have_exact_parity(self) -> None:
        comparison = self.result["guardrail_comparison"]
        self.assertEqual(comparison["legacy"], comparison["diverse_long_input"])
        self.assertEqual(comparison["errors"], 0)

    def test_locked_result_is_not_reused_for_new_version(self) -> None:
        self.assertFalse(self.result["decision"]["locked_result_reuse"])


if __name__ == "__main__":
    unittest.main()
