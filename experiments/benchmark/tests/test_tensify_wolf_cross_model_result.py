from __future__ import annotations

import json
import unittest
from pathlib import Path


BASELINE_DIR = Path(__file__).resolve().parents[1] / "baselines"
BASELINE = BASELINE_DIR / "tensify_wolf_cross_model_v1.json"
SEAL = BASELINE_DIR / "tensify_wolf_cross_model_seal_v1.json"


class TensifyWolfCrossModelResultTest(unittest.TestCase):
    def test_result_preserves_ood_interpretation_boundary(self) -> None:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        result = baseline["result"]
        self.assertEqual(result["evidence_status"], "VALID_OOD_REPLICATION")
        self.assertEqual(result["clean_blocked_attacks"], 20)
        self.assertTrue(result["baseline_coverage_gate"]["passed"])
        self.assertEqual(result["view_errors"], 0)
        self.assertIn("korean_ood", result["interpretation"])
        self.assertEqual(
            result["contamination_status"],
            "NO_EXACT_TEXT_AUDIT_SOURCE_OVERLAP_UNKNOWN",
        )

    def test_primary_policy_records_recovery_and_false_positive_cost(self) -> None:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        metrics = baseline["result"]["policies"]["ratio_0.10"]["metrics"]
        self.assertEqual(metrics["nrr"]["rows"], 2)
        self.assertEqual(metrics["nrr"]["micro_estimate"], 1.0)
        self.assertEqual(metrics["recovery_gain"]["micro_estimate"], 7 / 28)
        self.assertEqual(metrics["delta_fpr_clean"]["micro_estimate"], 0.0)
        self.assertEqual(metrics["delta_fpr_obfuscated"]["micro_estimate"], 6 / 28)

    def test_seal_forbids_tuning_and_promotion(self) -> None:
        seal = json.loads(SEAL.read_text(encoding="utf-8"))
        self.assertEqual(seal["policy"]["classifier_rule"], "argmax")
        self.assertEqual(seal["policy"]["injection_label_id"], 1)
        self.assertEqual(seal["interpretation"]["threshold_tuning"], "forbidden")
        self.assertEqual(seal["interpretation"]["promotion_decision"], "not_allowed")
        self.assertEqual(seal["interpretation"]["training_overlap"], "unknown_no_exact_text_audit")


if __name__ == "__main__":
    unittest.main()
