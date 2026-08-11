from __future__ import annotations

import json
import unittest
from pathlib import Path


BASELINE = (
    Path(__file__).resolve().parents[1]
    / "baselines"
    / "tensify_qwen_cross_model_v1.json"
)
SEAL = (
    Path(__file__).resolve().parents[1]
    / "baselines"
    / "tensify_qwen_cross_model_seal_v1.json"
)


class TensifyQwenCrossModelResultTest(unittest.TestCase):
    def test_repository_result_preserves_preregistered_boundary(self) -> None:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        result = baseline["result"]
        self.assertEqual(result["status"], "CROSS_MODEL_REPLICATION")
        self.assertEqual(result["evidence_status"], "LIMITED_BASELINE_COVERAGE")
        self.assertEqual(result["clean_blocked_attacks"], 15)
        self.assertFalse(result["baseline_coverage_gate"]["passed"])
        self.assertEqual(result["view_errors"], 0)
        self.assertEqual(result["provider_errors"], 0)
        self.assertEqual(
            baseline["provenance"]["model"]["revision"],
            "fada3b2f655b89601929198343c94cd2f64d93cc",
        )

    def test_primary_policy_records_limited_recovery_without_added_fpr(self) -> None:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        metrics = baseline["result"]["policies"]["ratio_0.10"]["metrics"]
        self.assertEqual(metrics["nrr"]["rows"], 3)
        self.assertEqual(metrics["nrr"]["micro_estimate"], 1.0)
        self.assertEqual(metrics["recovery_gain"]["micro_estimate"], 4 / 28)
        self.assertEqual(metrics["delta_fpr_clean"]["micro_estimate"], 0.0)
        self.assertEqual(metrics["delta_fpr_obfuscated"]["micro_estimate"], 0.0)
        self.assertEqual(metrics["raw_obfuscated_fpr"]["micro_estimate"], 17 / 28)

    def test_archived_seal_forbids_tuning_and_promotion(self) -> None:
        seal = json.loads(SEAL.read_text(encoding="utf-8"))
        self.assertEqual(seal["status"], "SEALED_NOT_EVALUATED")
        self.assertEqual(seal["interpretation"]["threshold_tuning"], "forbidden")
        self.assertEqual(seal["interpretation"]["promotion_decision"], "not_allowed")
        self.assertEqual(seal["policy"]["qwen_block_labels"], ["Controversial", "Unsafe"])


if __name__ == "__main__":
    unittest.main()
