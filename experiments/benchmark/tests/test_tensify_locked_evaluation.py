import json
import tempfile
import unittest
from pathlib import Path

from experiments.benchmark.run_clean_baseline import sha256_file
from experiments.benchmark.run_tensify_locked_evaluation import (
    make_decision,
    summarize_policy,
    validate_run_id,
    verify_seal,
)


def record(
    sample_id: str,
    label: str,
    technique: str,
    policy: str,
    blocked: bool,
    *,
    activated: bool = False,
    generated_views: int = 0,
) -> dict[str, object]:
    return {
        "sample_id": sample_id,
        "label": label,
        "technique": technique,
        "policy": policy,
        "policy_block": blocked,
        "policy_error": None,
        "activated": activated,
        "generated_view_count": generated_views,
        "lossless_mutation": False,
    }


def metric(estimate: float, low: float, high: float) -> dict[str, float]:
    return {
        "seed_balanced_estimate": estimate,
        "ci95_low": low,
        "ci95_high": high,
    }


class TensifyLockedEvaluationTest(unittest.TestCase):
    def test_run_id_rejects_path_characters(self) -> None:
        self.assertEqual(validate_run_id("locked-v1_2026.08"), "locked-v1_2026.08")
        with self.assertRaisesRegex(ValueError, "run-id"):
            validate_run_id("../escape")

    def test_seal_binds_dataset_selection_and_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "data.csv"
            selection = root / "selection.json"
            dataset.write_text("dataset\n", encoding="utf-8")
            selection.write_text(json.dumps({"selected": []}), encoding="utf-8")
            seal = {
                "status": "SEALED_NOT_EVALUATED",
                "dataset": {"sha256": sha256_file(dataset)},
                "source_selection": {"sha256": sha256_file(selection)},
                "policy": {
                    "candidate": "ratio_0.10",
                    "min_tense_syllables": 1,
                    "min_tense_ratio": 0.10,
                    "max_candidates": 9,
                    "max_views": 10,
                },
            }

            verify_seal(seal, dataset, selection)

            dataset.write_text("changed\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "dataset"):
                verify_seal(seal, dataset, selection)

            dataset.write_text("dataset\n", encoding="utf-8")
            seal["policy"]["min_tense_ratio"] = 0.20
            with self.assertRaisesRegex(ValueError, "activation"):
                verify_seal(seal, dataset, selection)

    def test_policy_summary_uses_paired_raw_baseline(self) -> None:
        records: list[dict[str, object]] = []
        for policy in ("raw", "ratio_0.10"):
            is_policy = policy != "raw"
            records.extend(
                [
                    record("attack", "attack", "clean", policy, True),
                    record(
                        "attack",
                        "attack",
                        "tensify",
                        policy,
                        is_policy,
                        activated=is_policy,
                        generated_views=int(is_policy),
                    ),
                    record("benign", "benign", "clean", policy, False),
                    record(
                        "benign",
                        "benign",
                        "tensify",
                        policy,
                        False,
                        activated=is_policy,
                        generated_views=int(is_policy),
                    ),
                ]
            )

        summary = summarize_policy(records, "ratio_0.10", 100, 2026)
        metrics = summary["metrics"]

        self.assertEqual(metrics["raw_cer"]["seed_balanced_estimate"], 1.0)
        self.assertEqual(metrics["residual_cer"]["seed_balanced_estimate"], 0.0)
        self.assertEqual(metrics["nrr"]["seed_balanced_estimate"], 1.0)
        self.assertEqual(metrics["recovery_gain"]["seed_balanced_estimate"], 1.0)
        self.assertEqual(metrics["delta_fpr_clean"]["seed_balanced_estimate"], 0.0)
        self.assertEqual(
            summary["transitions"]["attack_obfuscated_newly_blocked"], 1
        )

    def test_decision_promotes_preset_only_when_all_gates_pass(self) -> None:
        ratio_metrics = {
            "nrr": metric(0.8, 0.5, 1.0),
            "recovery_gain": metric(0.6, 0.2, 0.9),
            "delta_fpr_clean": metric(0.0, 0.0, 0.04),
            "delta_fpr_obfuscated": metric(0.0, 0.0, 0.04),
            "clean_mutation_rate": metric(0.0, 0.0, 0.0),
            "clean_activation_rate": metric(0.2, 0.1, 0.3),
            "clean_generated_view_count": metric(0.4, 0.2, 0.6),
        }
        all_metrics = {
            "nrr": metric(0.8, 0.5, 1.0),
            "clean_activation_rate": metric(1.0, 1.0, 1.0),
            "clean_generated_view_count": metric(2.0, 1.5, 2.5),
        }
        summary = {
            "view_errors": 0,
            "provider_errors": 0,
            "dataset_counts": {"benign_hard_negative": 28},
            "dataset_status": "SEALED_REVIEWED",
            "policies": {
                "ratio_0.10": {"metrics": ratio_metrics},
                "all": {"metrics": all_metrics},
            },
        }

        decision = make_decision(summary, clean_blocked_attacks=20, total_records=224)
        self.assertEqual(decision["status"], "RECOMMEND_RATIO_0.10_PRESET")
        self.assertEqual(decision["public_constructor_default"], 0.0)

        ratio_metrics["delta_fpr_clean"] = metric(0.03, 0.0, 0.06)
        decision = make_decision(summary, clean_blocked_attacks=20, total_records=224)
        self.assertEqual(decision["status"], "DO_NOT_PROMOTE")

        decision = make_decision(summary, clean_blocked_attacks=19, total_records=224)
        self.assertEqual(decision["status"], "INVALID_OR_INCONCLUSIVE")


if __name__ == "__main__":
    unittest.main()
