import unittest

from experiments.benchmark.run_ml_restore_evaluation import (
    build_summary,
    char_error_rate,
    observe_rows,
    summarize_group,
)


def _fake_restore(mapping: dict[str, tuple[str, float]]):
    """지정한 입력에만 후보를 내는 결정론적 복원기. 가중치 없이 집계 로직만 본다."""

    def restore(text: str) -> tuple[str, float | None]:
        return mapping.get(text, (text, None))

    return restore


class CharErrorRateTest(unittest.TestCase):
    def test_equal_length_counts_mismatched_characters(self) -> None:
        # Given / When / Then
        self.assertEqual(char_error_rate("가나다", "가나다"), 0.0)
        self.assertAlmostEqual(char_error_rate("가나다", "가나라"), 1 / 3)

    def test_different_length_uses_edit_distance(self) -> None:
        # Given / When / Then
        self.assertAlmostEqual(char_error_rate("가나다", "가나"), 1 / 3)
        self.assertAlmostEqual(char_error_rate("가", "가나다"), 2.0)

    def test_empty_reference(self) -> None:
        # Given / When / Then
        self.assertEqual(char_error_rate("", ""), 0.0)
        self.assertEqual(char_error_rate("", "가"), 1.0)


class ObserveRowsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [
            {
                "id": "atk-tensify",
                "seed_id": "a",
                "original": "가사",
                "text": "까싸",
                "label": "attack",
                "technique": "tensify",
                "intensity": 1.0,
            },
            {
                "id": "bng-clean",
                "seed_id": "b",
                "original": "진짜 좋다",
                "text": "진짜 좋다",
                "label": "benign",
                "technique": "clean",
                "intensity": 0,
            },
        ]

    def test_full_restoration_is_exact_and_removes_all_error(self) -> None:
        # Given
        restore = _fake_restore({"까싸": ("가사", 0.99)})
        # When
        observed = observe_rows(self.rows, restore=restore)
        # Then
        attack = observed[0]
        self.assertTrue(attack["changed"])
        self.assertTrue(attack["candidate_emitted"])
        self.assertTrue(attack["exact"])
        self.assertEqual(attack["residual_cer"], 0.0)
        self.assertEqual(attack["cer_reduction"], attack["raw_cer"])

    def test_silence_on_clean_input_is_not_a_mutation(self) -> None:
        # Given — 정상 문장에 후보를 내지 않으면 오변경이 아니다
        restore = _fake_restore({"까싸": ("가사", 0.99)})
        # When
        clean = observe_rows(self.rows, restore=restore)[1]
        # Then
        self.assertFalse(clean["candidate_emitted"])
        self.assertFalse(clean["mutated"])
        self.assertFalse(clean["changed"])
        self.assertEqual(clean["residual_cer"], 0.0)

    def test_touching_clean_input_counts_as_mutation(self) -> None:
        # Given — 정상 문장을 건드리면 오변경으로 잡혀야 한다
        restore = _fake_restore({"진짜 좋다": ("진자 좋다", 0.95)})
        # When
        clean = observe_rows(self.rows, restore=restore)[1]
        # Then
        self.assertTrue(clean["mutated"])
        self.assertFalse(clean["exact"])
        self.assertGreater(clean["residual_cer"], 0.0)
        self.assertLess(clean["cer_reduction"], 0.0)

    def test_partial_restoration_reduces_but_does_not_zero_error(self) -> None:
        # Given
        restore = _fake_restore({"까싸": ("가싸", 0.97)})
        # When
        attack = observe_rows(self.rows, restore=restore)[0]
        # Then
        self.assertFalse(attack["exact"])
        self.assertGreater(attack["cer_reduction"], 0.0)
        self.assertGreater(attack["residual_cer"], 0.0)


class SummaryTest(unittest.TestCase):
    def test_group_rates_use_changed_rows_for_restoration_metrics(self) -> None:
        # Given
        items = [
            {
                "changed": True, "candidate_emitted": True, "mutated": True,
                "exact": True, "raw_cer": 1.0, "residual_cer": 0.0,
                "cer_reduction": 1.0,
            },
            {
                "changed": False, "candidate_emitted": False, "mutated": False,
                "exact": False, "raw_cer": 0.0, "residual_cer": 0.0,
                "cer_reduction": 0.0,
            },
        ]
        # When
        summary = summarize_group(items)
        # Then
        self.assertEqual(summary["n"], 2)
        self.assertEqual(summary["changed_n"], 1)
        self.assertEqual(summary["candidate_generation_rate"], 0.5)
        self.assertEqual(summary["exact_restoration_rate"], 1.0)
        self.assertEqual(summary["mean_cer_reduction"], 1.0)

    def test_restoration_metrics_are_none_without_changed_rows(self) -> None:
        # Given
        items = [
            {
                "changed": False, "candidate_emitted": False, "mutated": False,
                "exact": False, "raw_cer": 0.0, "residual_cer": 0.0,
                "cer_reduction": 0.0,
            }
        ]
        # When
        summary = summarize_group(items)
        # Then
        self.assertIsNone(summary["exact_restoration_rate"])
        self.assertIsNone(summary["mean_cer_reduction"])

    def test_build_summary_splits_by_technique_intensity_and_label(self) -> None:
        # Given
        rows = [
            {
                "id": "a", "seed_id": "a", "original": "가사", "text": "까싸",
                "label": "attack", "technique": "tensify", "intensity": 1.0,
            },
            {
                "id": "b", "seed_id": "b", "original": "진짜", "text": "진짜",
                "label": "benign", "technique": "clean", "intensity": 0,
            },
        ]
        # When
        summary = build_summary(observe_rows(rows, restore=_fake_restore({})))
        # Then
        self.assertEqual(summary["overall"]["n"], 2)
        self.assertEqual(
            [(g["technique"], g["label"]) for g in summary["groups"]],
            [("clean", "benign"), ("tensify", "attack")],
        )


if __name__ == "__main__":
    unittest.main()
