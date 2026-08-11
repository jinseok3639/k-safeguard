import json
import tempfile
import unittest
from pathlib import Path

from experiments.benchmark.analyze_tensify_false_positives import (
    DEFAULT_OUTPUT,
    DEFAULT_PREDICTIONS,
    analyze,
    load_predictions,
)


def row(sample_id: str, policy: str, blocked: bool) -> dict[str, object]:
    return {
        "sample_id": sample_id,
        "subtype": "technical_meta",
        "text": "보안 테스트 명령을 실행합니다.",
        "tense_ratio": 0.1,
        "policy": policy,
        "activated": policy != "raw",
        "policy_block": blocked,
        "policy_category": "A1" if blocked else None,
        "policy_error": None,
        "trigger_view_index": 0 if blocked else None,
    }


class TensifyFalsePositiveAnalysisTest(unittest.TestCase):
    def test_requires_complete_policy_triplets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "predictions.jsonl"
            path.write_text('{"sample_id":"x","policy":"raw","policy_error":null}\n')
            with self.assertRaisesRegex(ValueError, "정확히 하나씩"):
                load_predictions(path)

    def test_analysis_separates_raw_error_from_candidate_transition(self) -> None:
        rows = [
            row("fp", "raw", True),
            row("fp", "all", True),
            row("fp", "ratio_0.10", True),
            row("safe", "raw", False),
            row("safe", "all", True),
            row("safe", "ratio_0.10", False),
        ]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "predictions.jsonl"
            source.write_text("fixture\n", encoding="utf-8")
            result = analyze(rows, source)

        self.assertEqual(result["raw_false_positive_count"], 1)
        self.assertEqual(result["policy_transitions_from_raw"]["all"]["newly_blocked"], 1)
        self.assertEqual(result["policy_transitions_from_raw"]["ratio_0.10"]["unchanged"], 2)
        self.assertIn("security_terms", result["false_positives"][0]["lexical_groups"])

    def test_repository_diagnostic_matches_frozen_dev_result(self) -> None:
        result = analyze(load_predictions(DEFAULT_PREDICTIONS), DEFAULT_PREDICTIONS)

        self.assertEqual(result["raw_false_positive_count"], 9)
        self.assertEqual(result["raw_false_positives_by_subtype"], {
            "mixed_format": 1,
            "technical_meta": 8,
        })
        self.assertEqual(result["policy_blocked_counts"], {
            "raw": 9,
            "all": 9,
            "ratio_0.10": 9,
        })
        self.assertEqual(
            result["policy_transitions_from_raw"]["ratio_0.10"], {"unchanged": 64}
        )
        frozen = json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))
        self.assertEqual(frozen, result)


if __name__ == "__main__":
    unittest.main()
