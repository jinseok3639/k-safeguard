import json
import unittest
from pathlib import Path

from experiments.benchmark.run_inverse_candidate_diagnostic import (
    evaluate,
    final_insertion_candidates,
    final_near_sound_candidates,
    liaison_candidates,
)


class InverseCandidateDiagnosticTest(unittest.TestCase):
    def test_generators_use_only_variant_text(self) -> None:
        self.assertIn("가나", set(final_insertion_candidates("간난", 8)))
        self.assertIn("밖", set(final_near_sound_candidates("박", 8)))
        self.assertEqual(list(liaison_candidates("머글게", 1)), ["먹을게"])

    def test_evaluate_counts_only_changed_rows(self) -> None:
        rows = [
            {
                "technique": "final_insertion",
                "text": "간",
                "original": "가",
            },
            {
                "technique": "final_insertion",
                "text": "가",
                "original": "가",
            },
            {
                "technique": "final_near_sound",
                "text": "박",
                "original": "밖",
            },
            {
                "technique": "liaison",
                "text": "머글게",
                "original": "먹을게",
            },
        ]

        result = evaluate(rows, [9])

        for technique in ("final_insertion", "final_near_sound", "liaison"):
            metric = result[technique]["by_candidate_limit"]["9"]
            self.assertEqual(metric["changed_rows"], 1)
            self.assertEqual(metric["exact_hits"], 1)
            self.assertEqual(metric["exact_hit_rate"], 1.0)

    def test_rejects_non_positive_candidate_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "1 이상"):
            evaluate([], [0])

    def test_checked_baseline_rates_match_counts(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "experiments"
            / "benchmark"
            / "baselines"
            / "inverse_candidate_v1.json"
        )
        baseline = json.loads(path.read_text(encoding="utf-8"))

        self.assertFalse(baseline["source"]["target_leakage"])
        for technique, result in baseline["metrics"].items():
            for limit, metric in result["by_candidate_limit"].items():
                with self.subTest(technique=technique, limit=limit):
                    self.assertAlmostEqual(
                        metric["exact_hit_rate"],
                        metric["exact_hits"] / result["changed_rows"],
                    )

    def test_checked_decision_keeps_low_recall_o2_out_of_runtime(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "experiments"
            / "benchmark"
            / "baselines"
            / "inverse_candidate_v1.json"
        )
        baseline = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(baseline["decision"]["ship_opt_in_provider"], ["liaison"])
        self.assertEqual(
            set(baseline["decision"]["defer_for_contextual_ranking"]),
            {"final_insertion", "final_near_sound"},
        )


if __name__ == "__main__":
    unittest.main()
