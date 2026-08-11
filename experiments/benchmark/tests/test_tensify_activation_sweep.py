import unittest

from experiments.benchmark.run_tensify_activation_sweep import (
    ActivationPolicy,
    apply_policy,
    summarize_activation,
    tense_evidence,
    validate_source_records,
)


def record(variant_id: str, policy: str, text: str, block: bool = False) -> dict:
    return {
        "variant_id": variant_id,
        "seed_id": variant_id,
        "label": "benign",
        "category": "benign_hard_negative",
        "technique": "clean",
        "intensity": 0.0,
        "policy": policy,
        "policy_block": block,
        "policy_error": None,
        "views": [{"text": text}],
    }


class TensifyActivationSweepTest(unittest.TestCase):
    def test_counts_tense_completed_hangul_only(self) -> None:
        self.assertEqual(tense_evidence("AI 진짜 짱!"), (2, 3, 2 / 3))
        self.assertEqual(tense_evidence("English 123"), (0, 0, 0.0))

    def test_policy_requires_count_and_ratio(self) -> None:
        policy = ActivationPolicy("candidate", 2, 0.1)

        self.assertTrue(policy.enabled(2, 0.1))
        self.assertFalse(policy.enabled(1, 0.5))
        self.assertFalse(policy.enabled(2, 0.09))

    def test_validates_pair_and_raw_view_containment(self) -> None:
        records = [record("v1", "raw", "진짜"), record("v1", "inverse", "진짜")]
        validate_source_records(records)

        with self.assertRaisesRegex(ValueError, "pair 누락"):
            validate_source_records(records[:1])
        invalid = [record("v1", "raw", "진짜"), record("v1", "inverse", "다른 view")]
        with self.assertRaisesRegex(ValueError, "보존"):
            validate_source_records(invalid)

    def test_inactive_policy_reuses_raw_decision_under_inverse_name(self) -> None:
        raw = record("v1", "raw", "진짜 좋아", block=False)
        inverse = record("v1", "inverse", "진짜 좋아", block=True)
        inverse["views"].append({"text": "진자 좋아"})

        selected, activation = apply_policy(
            [raw, inverse], ActivationPolicy("count_2", 2, 0.0)
        )

        chosen = next(item for item in selected if item["policy"] == "inverse")
        self.assertFalse(chosen["policy_block"])
        self.assertFalse(activation[0]["enabled"])

    def test_summarizes_activation_by_condition(self) -> None:
        groups = summarize_activation(
            [
                {"label": "benign", "technique": "clean", "intensity": 0.0, "enabled": True},
                {"label": "benign", "technique": "clean", "intensity": 0.0, "enabled": False},
            ]
        )

        self.assertEqual(groups[0]["activation_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
