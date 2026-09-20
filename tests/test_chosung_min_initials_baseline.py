import json
import unittest
from pathlib import Path


BASELINE = (
    Path(__file__).resolve().parents[1]
    / "experiments"
    / "benchmark"
    / "baselines"
    / "chosung_min_initials_v1.json"
)


class ChosungMinInitialsBaselineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = json.loads(BASELINE.read_text(encoding="utf-8"))

    def test_nrr_matches_recovery_counts(self) -> None:
        for minimum, result in self.result["guardrail_direct_policy"].items():
            nrr = result["nrr"]
            with self.subTest(minimum=minimum):
                self.assertAlmostEqual(
                    nrr["rate"],
                    nrr["recovered"] / nrr["raw_evasions_from_clean_block"],
                )

    def test_candidate_policy_never_loses_raw_blocks(self) -> None:
        for minimum, result in self.result["guardrail_direct_policy"].items():
            with self.subTest(minimum=minimum):
                self.assertGreaterEqual(
                    result["attack"]["candidate_blocked"],
                    result["attack"]["raw_blocked"],
                )
                self.assertGreaterEqual(
                    result["benign_obfuscated"]["candidate_blocked"],
                    result["benign_obfuscated"]["raw_blocked"],
                )

    def test_default_stays_at_three(self) -> None:
        self.assertEqual(self.result["decision"]["default_min_initials"], 3)
        self.assertEqual(self.result["decision"]["min_initials_2"], "explicit_opt_in")


if __name__ == "__main__":
    unittest.main()
