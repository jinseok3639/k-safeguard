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

    def test_liaison_guardrail_baseline_rates_match_counts(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "experiments"
            / "benchmark"
            / "baselines"
            / "liaison_guardrail_v1.json"
        )
        baseline = json.loads(path.read_text(encoding="utf-8"))
        guardrail = baseline["guardrail"]

        for group_name in ("attack_variants", "benign_variants", "clean_benign"):
            group = guardrail[group_name]
            self.assertAlmostEqual(
                group["raw_block_rate"] if "raw_block_rate" in group else group["raw_blocked"] / group["total"],
                group["raw_blocked"] / group["total"],
            )
            if "inverse_block_rate" in group:
                self.assertAlmostEqual(
                    group["inverse_block_rate"],
                    group["inverse_blocked"] / group["total"],
                )
            if "delta_fpr" in group:
                self.assertAlmostEqual(
                    group["delta_fpr"],
                    (group["inverse_blocked"] - group["raw_blocked"])
                    / group["total"],
                )

        recovery = guardrail["normalization_recovery"]
        self.assertEqual(
            recovery["raw_evasions_from_clean_block"],
            recovery["recovered_evasions"] + recovery["residual_evasions"],
        )
        self.assertAlmostEqual(
            recovery["variant_nrr"],
            recovery["recovered_evasions"]
            / recovery["raw_evasions_from_clean_block"],
        )

        cost = baseline["cost"]
        self.assertAlmostEqual(
            cost["truncated_rate"],
            cost["truncated_rows"] / cost["total_rows"],
        )


if __name__ == "__main__":
    unittest.main()
