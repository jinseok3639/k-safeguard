import csv
import tempfile
import unittest
from pathlib import Path

from experiments.benchmark.run_clean_baseline import (
    load_seed_rows,
    normalized_run_id,
    summarize,
)


FIELDNAMES = [
    "seed_id",
    "category",
    "subtype",
    "korean_text",
    "source_dataset",
    "source_group_id",
    "review_status",
]


def record(
    category: str,
    block: bool | None,
    predicted: str | None,
    error: str | None = None,
    review_status: str = "selected",
) -> dict:
    return {
        "category": category,
        "guardrail_block": block,
        "guardrail_category": predicted,
        "error_type": error,
        "latency_ms": 10.0,
        "review_status": review_status,
    }


class SeedLoaderTest(unittest.TestCase):
    def write_csv(self, directory: str, rows: list[dict]) -> Path:
        path = Path(directory) / "seeds.csv"
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_loads_category_and_null_group(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(
                directory,
                [
                    {
                        "seed_id": "seed-1",
                        "category": "A1_injection",
                        "subtype": "test",
                        "korean_text": "무해한 테스트 문장",
                        "source_dataset": "fixture",
                        "source_group_id": "",
                        "review_status": "team_review_needed",
                    }
                ],
            )
            rows = load_seed_rows(path)
        self.assertEqual(rows[0].expected_category, "A1")
        self.assertIsNone(rows[0].group_id)

    def test_filters_review_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(
                directory,
                [
                    {
                        "seed_id": "seed-1",
                        "category": "A1_injection",
                        "subtype": "test",
                        "korean_text": "첫 문장",
                        "source_dataset": "fixture",
                        "source_group_id": "g1",
                        "review_status": "selected",
                    },
                    {
                        "seed_id": "seed-2",
                        "category": "A2_leaking",
                        "subtype": "test",
                        "korean_text": "둘째 문장",
                        "source_dataset": "fixture",
                        "source_group_id": "g2",
                        "review_status": "team_review_needed",
                    },
                ],
            )
            rows = load_seed_rows(path, review_statuses={"selected"})
        self.assertEqual([row.seed_id for row in rows], ["seed-1"])

    def test_rejects_duplicate_seed_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(
                directory,
                [
                    {
                        "seed_id": "duplicate",
                        "category": "A1_injection",
                        "subtype": "test",
                        "korean_text": "첫 문장",
                        "source_dataset": "fixture",
                        "source_group_id": "g1",
                        "review_status": "selected",
                    },
                    {
                        "seed_id": "duplicate",
                        "category": "A2_leaking",
                        "subtype": "test",
                        "korean_text": "둘째 문장",
                        "source_dataset": "fixture",
                        "source_group_id": "g2",
                        "review_status": "selected",
                    },
                ],
            )
            with self.assertRaisesRegex(ValueError, "중복 seed_id"):
                load_seed_rows(path)


class SummaryTest(unittest.TestCase):
    def test_gate_passes_at_twenty_blocks_without_errors(self) -> None:
        records = [record("A1", True, "A1") for _ in range(10)]
        records += [record("A2", True, "A2") for _ in range(10)]
        summary = summarize(records)
        self.assertTrue(summary["technical_gate"]["passed"])
        self.assertEqual(summary["overall_validity"], "INCOMPLETE")

    def test_category_mismatch_is_block_but_not_category_match(self) -> None:
        summary = summarize([record("A1", True, "A2")])
        self.assertEqual(summary["blocked"], 1)
        self.assertEqual(summary["category_matches"], 0)

    def test_invalid_output_is_not_counted_as_miss(self) -> None:
        summary = summarize([record("A1", None, None, "invalid_output")])
        self.assertEqual(summary["missed"], 0)
        self.assertEqual(summary["invalid_outputs"], 1)

    def test_review_pending_marks_result_provisional(self) -> None:
        summary = summarize(
            [record("A1", True, "A1", review_status="team_review_needed")]
        )
        self.assertTrue(summary["provisional"])


class RunIdTest(unittest.TestCase):
    def test_rejects_path_characters(self) -> None:
        with self.assertRaises(ValueError):
            normalized_run_id("../overwrite")


if __name__ == "__main__":
    unittest.main()
