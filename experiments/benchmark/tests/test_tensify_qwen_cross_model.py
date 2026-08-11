from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from experiments.benchmark.run_clean_baseline import sha256_file
from experiments.benchmark.run_tensify_qwen_cross_model import (
    MODEL_KEY,
    PROTOCOL_VERSION,
    REPO_ROOT,
    verify_seal,
)


class TensifyQwenCrossModelTest(unittest.TestCase):
    def make_seal(self, input_path: Path, selection_path: Path) -> dict:
        runner = REPO_ROOT / "experiments" / "benchmark" / "run_tensify_qwen_cross_model.py"
        adapter = REPO_ROOT / "experiments" / "benchmark" / "adapters" / "qwen3guard_gen.py"
        return {
            "protocol_version": PROTOCOL_VERSION,
            "status": "SEALED_NOT_EVALUATED",
            "dataset": {"sha256": sha256_file(input_path)},
            "source_selection": {"sha256": sha256_file(selection_path)},
            "model": {
                "key": MODEL_KEY,
                "model_id": "Qwen/Qwen3Guard-Gen-0.6B",
                "revision": "revision",
                "dtype": "bfloat16",
            },
            "policy": {
                "primary": "ratio_0.10",
                "secondary": "all",
                "min_tense_syllables": 1,
                "min_tense_ratio": 0.10,
                "max_candidates": 9,
                "max_views": 10,
                "qwen_block_labels": ["Controversial", "Unsafe"],
                "max_new_tokens": 48,
            },
            "implementation": {
                "git": {"commit": "commit", "dirty": False},
                "runner_sha256": sha256_file(runner),
                "adapter_sha256": sha256_file(adapter),
            },
        }

    def test_seal_binds_qwen_rule_and_implementation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "input.csv"
            selection_path = root / "selection.json"
            input_path.write_text("input", encoding="utf-8")
            selection_path.write_text("{}", encoding="utf-8")
            model_spec = {
                "model_id": "Qwen/Qwen3Guard-Gen-0.6B",
                "revision": "revision",
                "inference_dtype": "bfloat16",
            }
            seal = self.make_seal(input_path, selection_path)
            with patch(
                "experiments.benchmark.run_tensify_qwen_cross_model.git_metadata",
                return_value={"commit": "commit", "dirty": False},
            ):
                verify_seal(seal, input_path, selection_path, model_spec)
                changed = deepcopy(seal)
                changed["policy"]["qwen_block_labels"] = ["Unsafe"]
                with self.assertRaisesRegex(ValueError, "사전등록 정책"):
                    verify_seal(changed, input_path, selection_path, model_spec)

    def test_model_revision_is_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "input.csv"
            selection_path = root / "selection.json"
            input_path.write_text("input", encoding="utf-8")
            selection_path.write_text(json.dumps({}), encoding="utf-8")
            seal = self.make_seal(input_path, selection_path)
            wrong_spec = {
                "model_id": "Qwen/Qwen3Guard-Gen-0.6B",
                "revision": "different",
                "inference_dtype": "bfloat16",
            }
            with self.assertRaisesRegex(ValueError, "모델 규격"):
                verify_seal(seal, input_path, selection_path, wrong_spec)


if __name__ == "__main__":
    unittest.main()
