import unittest

from experiments.benchmark.run_chosung_candidate_ranking_diagnostic import (
    strategy_key,
    summarize_observations,
)


def candidate(
    index: int,
    *,
    block: bool,
    source_rank: int,
    all_domain: bool,
) -> dict:
    return {
        "block": block,
        "features": {
            "text": f"candidate-{index}",
            "original_index": index,
            "layer": "direct",
            "layer_rank": 0,
            "all_priority_source": all_domain,
            "source_rank_sum": source_rank,
            "covered_initials": 3,
            "replacement_count": 1,
            "rank_score": index,
        },
    }


class CandidateRankingDiagnosticTest(unittest.TestCase):
    def test_unknown_strategy_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "strategy"):
            strategy_key("unknown", candidate(1, block=False, source_rank=0, all_domain=True))

    def test_current_order_can_outperform_source_first_without_label_leakage(self) -> None:
        observations = [
            {
                "label": "attack",
                "raw_block": False,
                "recovery_eligible": True,
                "candidates": [
                    candidate(1, block=True, source_rank=1, all_domain=False),
                    candidate(2, block=False, source_rank=0, all_domain=True),
                ],
            },
            {
                "label": "benign",
                "raw_block": False,
                "recovery_eligible": False,
                "candidates": [
                    candidate(1, block=False, source_rank=1, all_domain=False),
                    candidate(2, block=False, source_rank=0, all_domain=True),
                ],
            },
        ]

        summary = summarize_observations(observations, budgets=(2, 3))

        current = summary["strategies"]["current"]["budgets"][0]
        source_first = summary["strategies"]["source_first"]["budgets"][0]
        self.assertEqual(current["nrr_micro"], 1.0)
        self.assertEqual(source_first["nrr_micro"], 0.0)
        self.assertEqual(summary["first_recovery_candidate_rank"], {"1": 1})
        self.assertEqual(summary["recovery_layer"], {"direct": 1})


if __name__ == "__main__":
    unittest.main()
