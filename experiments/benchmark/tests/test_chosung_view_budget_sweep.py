import argparse
import unittest

from experiments.benchmark.run_chosung_view_budget_sweep import (
    cap_policy_record,
    compact_policy_curve,
    parse_budgets,
    summarize_budget,
)


def record(
    policy: str,
    label: str,
    blocks: tuple[bool, ...],
    *,
    technique: str = "chosung",
) -> dict:
    return {
        "variant_id": f"{technique}-{label}",
        "seed_id": label,
        "label": label,
        "category": "A1_injection" if label == "attack" else "benign_hard_negative",
        "technique": technique,
        "intensity": 0.0 if technique == "clean" else 1.0,
        "policy": policy,
        "policy_block": any(blocks),
        "policy_category": None,
        "policy_error": None,
        "trigger_view_index": next((i for i, block in enumerate(blocks) if block), None),
        "view_count": len(blocks),
        "generated_view_count": len(blocks) - 1,
        "model_latency_sum_ms": float(len(blocks)),
        "truncated": False,
        "views": [
            {
                "text": f"{technique}-{label}-{index}",
                "block": block,
                "category": "A1" if block else None,
                "error_type": None,
                "latency_ms": 1.0,
            }
            for index, block in enumerate(blocks)
        ],
    }


class ViewBudgetTest(unittest.TestCase):
    def test_parses_sorted_unique_positive_budgets(self) -> None:
        self.assertEqual(parse_budgets("8,2,8,4"), (2, 4, 8))
        with self.assertRaisesRegex(argparse.ArgumentTypeError, "양의 정수"):
            parse_budgets("0,2")

    def test_cap_reaggregates_only_retained_prefix(self) -> None:
        capped = cap_policy_record(record("segmented", "attack", (False, False, True)), 2)

        self.assertFalse(capped["policy_block"])
        self.assertEqual(capped["view_count"], 2)
        self.assertEqual(capped["generated_view_count"], 1)
        self.assertTrue(capped["truncated"])
        self.assertEqual(len(capped["views"]), 2)

    def test_larger_budget_recovers_later_block_without_changing_raw(self) -> None:
        records = []
        for policy in ("raw", "direct", "segmented", "partial"):
            blocks = (False,) if policy == "raw" else (False, False, True)
            records.append(record(policy, "attack", blocks))
            records.append(record(policy, "benign", (False,) * len(blocks)))
            records.append(record(policy, "attack", (True,), technique="clean"))
            records.append(record(policy, "benign", (False,), technique="clean"))

        small = summarize_budget(records, 2, 0, 2026)
        large = summarize_budget(records, 3, 0, 2026)

        self.assertEqual(
            small["policy_metrics"]["segmented"]["attack_block_rate"]["micro_estimate"],
            0.0,
        )
        self.assertEqual(
            large["policy_metrics"]["segmented"]["attack_block_rate"]["micro_estimate"],
            1.0,
        )
        self.assertEqual(small["policy_costs"]["raw"]["mean_total_views"], 1.0)

        summary = {
            "status": "PROVISIONAL_DEV_ONLY",
            "source": {"run_id": "test"},
            "method": "prefix replay",
            "bootstrap_samples": 0,
            "random_seed": 2026,
            "budgets": [large],
        }
        compact = compact_policy_curve(summary, "segmented")
        self.assertEqual(compact["budgets"][0]["budget"], 3)
        self.assertNotIn("policy_metrics", compact["budgets"][0])


if __name__ == "__main__":
    unittest.main()
