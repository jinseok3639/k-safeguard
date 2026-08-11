import json
import tempfile
import unittest
from pathlib import Path

from experiments.benchmark.freeze_tensify_locked_result import (
    DEFAULT_OUTPUT,
    freeze_result,
)
from experiments.benchmark.run_clean_baseline import sha256_file


class FreezeTensifyLockedResultTest(unittest.TestCase):
    def test_rejects_incomplete_result_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "artifact 누락"):
                freeze_result(Path(directory))

    def test_repository_baseline_matches_local_locked_result(self) -> None:
        result_dir = (
            DEFAULT_OUTPUT.parents[1]
            / "results"
            / "tensify-locked-v2-20260811"
        )
        frozen = freeze_result(result_dir)
        baseline = json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))

        self.assertEqual(frozen, baseline)
        self.assertEqual(
            baseline["result"]["decision"]["status"], "DO_NOT_PROMOTE"
        )
        self.assertEqual(baseline["result"]["clean_blocked_attacks"], 23)
        self.assertEqual(baseline["result"]["view_errors"], 0)
        self.assertEqual(
            baseline["artifact_sha256"]["summary.json"],
            sha256_file(result_dir / "summary.json"),
        )


if __name__ == "__main__":
    unittest.main()
