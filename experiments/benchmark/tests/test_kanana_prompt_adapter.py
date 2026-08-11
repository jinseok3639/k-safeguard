import unittest

from experiments.benchmark.adapters.kanana_prompt import (
    hash_token_ids,
    normalize_device_map,
    parse_kanana_prompt_output,
)


class ParseKananaPromptOutputTest(unittest.TestCase):
    def test_safe(self) -> None:
        self.assertEqual(parse_kanana_prompt_output("<SAFE>"), (False, None, None))

    def test_a1(self) -> None:
        self.assertEqual(parse_kanana_prompt_output("<UNSAFE-A1>"), (True, "A1", None))

    def test_a2_with_surrounding_whitespace(self) -> None:
        self.assertEqual(parse_kanana_prompt_output("  <UNSAFE-A2>\n"), (True, "A2", None))

    def test_unknown_is_invalid_not_safe(self) -> None:
        self.assertEqual(parse_kanana_prompt_output("UNKNOWN"), (None, None, "invalid_output"))

    def test_token_hash_is_deterministic_and_order_sensitive(self) -> None:
        self.assertEqual(hash_token_ids([1, 2, 3]), hash_token_ids([1, 2, 3]))
        self.assertNotEqual(hash_token_ids([1, 2, 3]), hash_token_ids([3, 2, 1]))

    def test_device_map_replaces_empty_root_key(self) -> None:
        self.assertEqual(normalize_device_map({"": 0}), {"<root>": "0"})


if __name__ == "__main__":
    unittest.main()
