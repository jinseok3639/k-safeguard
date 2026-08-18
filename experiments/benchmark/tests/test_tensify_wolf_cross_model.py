from __future__ import annotations

import copy
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.benchmark.run_clean_baseline import sha256_file
from experiments.benchmark.run_tensify_wolf_cross_model import (
    ADAPTER_PATH,
    MODEL_KEY,
    PROTOCOL_VERSION,
    expected_policy,
    verify_seal,
)
from experiments.benchmark.validate_tensify_locked_set import DEFAULT_INPUT, DEFAULT_SELECTION


REPO_ROOT = Path(__file__).resolve().parents[3]


class TensifyWolfCrossModelSealTest(unittest.TestCase):
    def setUp(self) -> None:
        self.input_path = DEFAULT_INPUT
        self.selection_path = DEFAULT_SELECTION
        self.runner = REPO_ROOT / "experiments" / "benchmark" / "run_tensify_wolf_cross_model.py"
        self.model_spec = {
            "model_id": "patronus-studio/wolf-defender-prompt-injection",
            "revision": "revision",
            "inference_dtype": "float32",
        }
        self.seal = {
            "protocol_version": PROTOCOL_VERSION,
            "status": "SEALED_NOT_EVALUATED",
            "dataset": {"sha256": sha256_file(self.input_path)},
            "source_selection": {"sha256": sha256_file(self.selection_path)},
            "model": {
                "key": MODEL_KEY,
                "model_id": self.model_spec["model_id"],
                "revision": self.model_spec["revision"],
                "dtype": self.model_spec["inference_dtype"],
            },
            "policy": expected_policy(),
            "implementation": {
                "git": {"commit": "abc", "dirty": False},
                "runner_sha256": sha256_file(self.runner),
                "adapter_sha256": sha256_file(ADAPTER_PATH),
            },
        }

    @patch(
        "experiments.benchmark.run_tensify_wolf_cross_model.git_metadata",
        return_value={"commit": "abc", "dirty": False},
    )
    def test_seal_binds_argmax_rule_and_implementation(self, _mock: object) -> None:
        verify_seal(self.seal, self.input_path, self.selection_path, self.model_spec)

    @patch(
        "experiments.benchmark.run_tensify_wolf_cross_model.git_metadata",
        return_value={"commit": "abc", "dirty": False},
    )
    def test_changed_label_rule_is_rejected(self, _mock: object) -> None:
        changed = copy.deepcopy(self.seal)
        changed["policy"]["injection_label_id"] = 0
        with self.assertRaisesRegex(ValueError, "사전등록 정책"):
            verify_seal(changed, self.input_path, self.selection_path, self.model_spec)


if __name__ == "__main__":
    unittest.main()
