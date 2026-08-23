import unittest

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


if __name__ == "__main__":
    unittest.main()
