from __future__ import annotations

import unittest

from experiments.benchmark.adapters.qwen3guard_gen import parse_qwen3guard_output


class Qwen3GuardOutputTest(unittest.TestCase):
    def test_safe_none_is_allowed(self) -> None:
        self.assertEqual(
            parse_qwen3guard_output("Safety: Safe\nCategories: None"),
            (False, None, None),
        )

    def test_unsafe_jailbreak_is_blocked(self) -> None:
        self.assertEqual(
            parse_qwen3guard_output("Safety: Unsafe\nCategories: Jailbreak"),
            (True, "Jailbreak", None),
        )

    def test_controversial_policy_is_explicit(self) -> None:
        raw = "Safety: Controversial\nCategories: Unethical Acts"
        self.assertEqual(
            parse_qwen3guard_output(raw),
            (True, "Unethical Acts", None),
        )
        self.assertEqual(
            parse_qwen3guard_output(raw, block_controversial=False),
            (False, "Unethical Acts", None),
        )

    def test_multiple_categories_are_preserved(self) -> None:
        self.assertEqual(
            parse_qwen3guard_output(
                "Safety: Unsafe\nCategories: Jailbreak, Non-violent Illegal Acts"
            ),
            (True, "Jailbreak,Non-violent Illegal Acts", None),
        )

    def test_malformed_output_is_invalid(self) -> None:
        invalid = (
            "Safety: Unknown\nCategories: None",
            "Safety: Safe",
            "Safety: Safe\nCategories: Made Up",
            "Safety: Safe\nCategories: None, Jailbreak",
        )
        for raw in invalid:
            with self.subTest(raw=raw):
                self.assertEqual(
                    parse_qwen3guard_output(raw),
                    (None, None, "invalid_output"),
                )


if __name__ == "__main__":
    unittest.main()
