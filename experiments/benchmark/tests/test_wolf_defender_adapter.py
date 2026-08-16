from __future__ import annotations

import unittest

from experiments.benchmark.adapters.wolf_defender import parse_wolf_defender_label


class WolfDefenderOutputTest(unittest.TestCase):
    def test_benign_label_is_allowed(self) -> None:
        self.assertEqual(parse_wolf_defender_label(0), (False, None, None))

    def test_injection_label_is_blocked(self) -> None:
        self.assertEqual(
            parse_wolf_defender_label(1),
            (True, "prompt_injection", None),
        )

    def test_unknown_label_is_invalid(self) -> None:
        self.assertEqual(
            parse_wolf_defender_label(2),
            (None, None, "invalid_output"),
        )


if __name__ == "__main__":
    unittest.main()
