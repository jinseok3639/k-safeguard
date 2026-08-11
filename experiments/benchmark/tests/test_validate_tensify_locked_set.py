import json
import unittest
from dataclasses import replace

from experiments.benchmark.run_clean_baseline import sha256_file
from experiments.benchmark.validate_tensify_locked_set import (
    DEFAULT_INPUT,
    DEFAULT_SELECTION,
    build_seal,
    load_candidates,
    load_reference_texts,
    validate_candidates,
)


class ValidateTensifyLockedSetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = load_candidates(DEFAULT_INPUT)
        cls.selection = json.loads(DEFAULT_SELECTION.read_text(encoding="utf-8"))

    def test_repository_candidates_are_frozen_but_review_pending(self) -> None:
        summary = validate_candidates(
            self.rows, self.selection, load_reference_texts()
        )

        self.assertEqual(summary["status"], "REVIEW_PENDING")
        self.assertEqual(summary["rows"], 56)
        self.assertEqual(summary["tensify_changed"], 56)
        self.assertEqual(summary["exact_overlap_count"], 0)
        self.assertEqual(
            self.selection["translation_candidate"]["sha256"],
            sha256_file(DEFAULT_INPUT),
        )

    def test_source_provenance_change_is_rejected(self) -> None:
        changed = list(self.rows)
        changed[0] = replace(changed[0], source_row=999999)

        with self.assertRaisesRegex(ValueError, "source selection 불일치"):
            validate_candidates(changed, self.selection, {})

        changed = list(self.rows)
        changed[0] = replace(changed[0], source_text="changed source")
        with self.assertRaisesRegex(ValueError, "source text SHA-256"):
            validate_candidates(changed, self.selection, {})

        changed = list(self.rows)
        changed[0] = replace(changed[0], source_revision="floating-main")
        with self.assertRaisesRegex(ValueError, "dataset/revision"):
            validate_candidates(changed, self.selection, {})

    def test_development_text_overlap_is_rejected(self) -> None:
        first = self.rows[0]
        with self.assertRaisesRegex(ValueError, "exact text 중복"):
            validate_candidates(
                self.rows,
                self.selection,
                {"dev": {first.text.casefold()}},
            )

    def test_seal_requires_every_row_reviewed(self) -> None:
        summary = validate_candidates(self.rows, self.selection, {})
        with self.assertRaisesRegex(ValueError, "selected"):
            build_seal(DEFAULT_INPUT, DEFAULT_SELECTION, self.rows, summary)

        reviewed = [replace(row, review_status="selected") for row in self.rows]
        reviewed_summary = validate_candidates(reviewed, self.selection, {})
        seal = build_seal(DEFAULT_INPUT, DEFAULT_SELECTION, reviewed, reviewed_summary)
        self.assertEqual(seal["status"], "SEALED_NOT_EVALUATED")
        self.assertTrue(seal["rules"]["run_once_after_sealing"])


if __name__ == "__main__":
    unittest.main()
