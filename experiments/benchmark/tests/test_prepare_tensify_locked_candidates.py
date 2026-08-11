import unittest

from experiments.benchmark.prepare_tensify_locked_candidates import (
    BUCKET_QUOTAS,
    QUOTAS,
    canonical_source_text,
    normalized_source_text,
    select_candidates,
    selection_key,
    source_text_sha256,
)


def source_row(
    category: str,
    group_id: str,
    text: str,
    *,
    source: str = "original",
) -> dict:
    return {
        "category": category,
        "group_id": group_id,
        "text": text,
        "source": source,
    }


class PrepareTensifyLockedCandidatesTest(unittest.TestCase):
    def test_hashes_are_deterministic_and_text_normalization_is_bounded(self) -> None:
        self.assertEqual(canonical_source_text("  Ignore\n  this  "), "Ignore this")
        self.assertEqual(selection_key("group"), selection_key("group"))
        self.assertNotEqual(selection_key("group"), selection_key("other"))
        self.assertEqual(source_text_sha256("text"), source_text_sha256("text"))
        self.assertEqual(normalized_source_text("  Hello\n WORLD "), "hello world")

    def test_selects_fixed_quotas_without_model_predictions(self) -> None:
        rows = {"train": [], "validation": [], "test": []}
        for index in range(BUCKET_QUOTAS["a1_original"] + 3):
            rows["test"].append(source_row("direct_injection", f"a1-{index}", f"attack {index}"))
        for index in range(BUCKET_QUOTAS["a1_external"] + 3):
            rows["test"].append(
                source_row(
                    "direct_injection",
                    f"a1-ext-{index}",
                    f"ignore previous instruction {index}",
                    source="hackaprompt",
                )
            )
        for index in range(BUCKET_QUOTAS["a2_original"] + 2):
            split = ("train", "validation", "test")[index % 3]
            rows[split].append(source_row("prompt_extraction", f"a2-{index}", f"leak {index}"))
        for index in range(BUCKET_QUOTAS["a2_external"] + 2):
            split = ("train", "validation", "test")[index % 3]
            rows[split].append(
                source_row(
                    "prompt_extraction",
                    f"a2-ext-{index}",
                    f"show prompt {index}",
                    source="hackaprompt",
                )
            )
        for index in range(BUCKET_QUOTAS["benign_original"] + 3):
            rows["test"].append(source_row("benign", f"b-{index}", f"benign {index}"))

        selected = select_candidates(rows, {"a1-0", "a2-0", "b-0"})

        for category, quota in QUOTAS.items():
            category_rows = [row for row in selected if row["category"] == category]
            self.assertEqual(len(category_rows), quota)
            self.assertEqual(
                [row["selection_rank"] for row in category_rows],
                list(range(1, quota + 1)),
            )
        self.assertTrue(all(row["review_status"] == "team_review_needed" for row in selected))
        self.assertNotIn("a1-0", {row["source_group_id"] for row in selected})

    def test_rejects_non_ascii_and_duplicate_source_text(self) -> None:
        rows = {"train": [], "validation": [], "test": []}
        for index in range(BUCKET_QUOTAS["a1_original"] + 1):
            rows["test"].append(source_row("direct_injection", f"a1-{index}", f"attack {index}"))
        rows["test"].append(source_row("direct_injection", "non-ascii", "공격"))
        rows["test"].append(source_row("direct_injection", "duplicate", " ATTACK 1 "))
        for index in range(BUCKET_QUOTAS["a1_external"]):
            rows["test"].append(
                source_row(
                    "direct_injection",
                    f"a1-ext-{index}",
                    f"ignore context {index}",
                    source="other",
                )
            )
        for index in range(BUCKET_QUOTAS["a2_original"]):
            rows["train"].append(source_row("system_extraction", f"a2-{index}", f"leak {index}"))
        for index in range(BUCKET_QUOTAS["a2_external"]):
            rows["train"].append(
                source_row(
                    "prompt_extraction",
                    f"a2-ext-{index}",
                    f"show prompt {index}",
                    source="other",
                )
            )
        for index in range(BUCKET_QUOTAS["benign_original"]):
            rows["test"].append(source_row("benign", f"b-{index}", f"benign {index}"))

        selected = select_candidates(rows, set())
        groups = {row["source_group_id"] for row in selected}

        self.assertNotIn("non-ascii", groups)
        self.assertNotIn("duplicate", groups)

    def test_fails_when_a_quota_cannot_be_filled(self) -> None:
        with self.assertRaisesRegex(ValueError, "후보 부족"):
            select_candidates({"train": [], "validation": [], "test": []}, set())


if __name__ == "__main__":
    unittest.main()
