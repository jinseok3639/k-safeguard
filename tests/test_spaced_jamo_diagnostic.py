import json
import unittest
from pathlib import Path

from experiments.benchmark.run_spaced_jamo_diagnostic import evaluate, space_one_word


class SpacedJamoDiagnosticTest(unittest.TestCase):
    def test_spaces_only_one_eligible_word(self) -> None:
        variant = space_one_word("값이 없다")

        self.assertEqual(variant, "ㄱ ㅏ ㅂ ㅅ ㅇ ㅣ 없다")

    def test_skips_text_without_bounded_hangul_word(self) -> None:
        self.assertIsNone(space_one_word("API 123"))
        self.assertIsNone(space_one_word("가", min_jamo=4))

    def test_evaluate_keeps_default_lossless_and_restores_exact_candidate(self) -> None:
        metrics = evaluate(
            [
                {"text": "값이 없다"},
                {"text": "시스템 점검"},
                {"text": "API 123"},
            ]
        )

        self.assertEqual(metrics["seed_count"], 3)
        self.assertEqual(metrics["eligible_variants"], 2)
        self.assertEqual(metrics["provider_activated"], 2)
        self.assertEqual(metrics["exact_restored"], 2)
        self.assertEqual(metrics["exact_restoration_rate"], 1.0)
        self.assertEqual(metrics["default_gateway_changed"], 0)
        self.assertEqual(metrics["clean_provider_activated"], 0)
        self.assertFalse(metrics["target_leakage"])

    def test_checked_baseline_is_internally_consistent(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "experiments"
            / "benchmark"
            / "baselines"
            / "spaced_jamo_v1.json"
        )
        baseline = json.loads(path.read_text(encoding="utf-8"))
        population = baseline["population"]
        metrics = baseline["metrics"]

        self.assertFalse(baseline["source"]["target_leakage"])
        self.assertEqual(
            metrics["provider_activated"], population["eligible_variants"]
        )
        self.assertEqual(metrics["exact_restored"], population["eligible_variants"])
        self.assertAlmostEqual(
            metrics["exact_restoration_rate"],
            metrics["exact_restored"] / population["eligible_variants"],
        )
        self.assertEqual(metrics["default_gateway_changed"], 0)
        self.assertEqual(metrics["clean_provider_activated"], 0)


if __name__ == "__main__":
    unittest.main()
