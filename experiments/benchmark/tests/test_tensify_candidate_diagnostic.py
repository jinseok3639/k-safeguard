import unittest

from experiments.benchmark.run_tensify_candidate_diagnostic import (
    build_summary,
    observe_rows,
)


class TensifyCandidateDiagnosticTest(unittest.TestCase):
    def test_observes_exact_rank_and_clean_candidate_cost(self) -> None:
        rows = [
            {
                "id": "attack",
                "seed_id": "a",
                "original": "가사",
                "text": "까싸",
                "label": "attack",
                "category": "A1",
                "technique": "tensify",
                "intensity": 1.0,
            },
            {
                "id": "clean",
                "seed_id": "b",
                "original": "진짜",
                "text": "진짜",
                "label": "benign",
                "category": "benign_hard_negative",
                "technique": "clean",
                "intensity": 0.0,
            },
        ]

        observations = observe_rows(rows, max_candidates=3)

        self.assertEqual(observations[0]["exact_rank"], 1)
        self.assertEqual(observations[0]["candidate_count"], 3)
        self.assertFalse(observations[0]["truncated"])
        self.assertTrue(observations[1]["candidate_generated"])
        self.assertFalse(observations[1]["exact_hit"])

    def test_summarizes_by_technique_label_and_intensity(self) -> None:
        observations = observe_rows(
            [
                {
                    "id": "a",
                    "seed_id": "a",
                    "original": "가",
                    "text": "까",
                    "label": "attack",
                    "category": "A1",
                    "technique": "tensify",
                    "intensity": 1.0,
                },
                {
                    "id": "b",
                    "seed_id": "b",
                    "original": "나",
                    "text": "나",
                    "label": "attack",
                    "category": "A1",
                    "technique": "tensify",
                    "intensity": 1.0,
                },
            ],
            max_candidates=9,
        )

        summary = build_summary(observations)

        self.assertEqual(summary["overall"]["n"], 2)
        self.assertEqual(summary["groups"][0]["exact_hit_rate"], 0.5)
        self.assertEqual(summary["groups"][0]["changed_exact_hit_rate"], 1.0)
        self.assertEqual(summary["groups"][0]["candidate_generation_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
