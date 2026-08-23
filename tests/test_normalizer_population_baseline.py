import json
import unittest
from pathlib import Path


BASELINE = (
    Path(__file__).resolve().parents[1]
    / "experiments"
    / "benchmark"
    / "baselines"
    / "normalizer_population_v1.json"
)


class NormalizerPopulationBaselineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = json.loads(BASELINE.read_text(encoding="utf-8"))

    def test_attack_rates_and_gain_match_counts(self) -> None:
        groups = [
            value["all_attack_variants"]
            for value in self.result["techniques"].values()
        ]
        groups.append(
            self.result["combined_supported_techniques"]["all_attack_variants"]
        )
        for group in groups:
            with self.subTest(group=group):
                e1_rate = group["e1_blocked"] / group["total"]
                e2_rate = group["e2_blocked"] / group["total"]
                self.assertAlmostEqual(group["e1_block_rate"], e1_rate)
                self.assertAlmostEqual(group["e2_block_rate"], e2_rate)
                self.assertAlmostEqual(group["recovery_gain"], e2_rate - e1_rate)

    def test_combined_counts_equal_technique_sums(self) -> None:
        combined = self.result["combined_supported_techniques"]
        for population in ("all_attack_variants", "changed_attack_variants"):
            with self.subTest(population=population):
                technique_groups = [
                    value[population]
                    for value in self.result["techniques"].values()
                ]
                for field in ("e1_blocked", "e2_blocked", "total"):
                    self.assertEqual(
                        combined[population][field],
                        sum(group[field] for group in technique_groups),
                    )

    def test_changed_evasions_are_fully_recovered(self) -> None:
        for technique, value in self.result["techniques"].items():
            group = value["changed_attack_variants"]
            with self.subTest(technique=technique):
                self.assertEqual(
                    group["raw_evasions_from_clean_block"],
                    group["recovered_evasions"],
                )
                self.assertEqual(group["residual_evasions"], 0)

    def test_exact_restoration_counts_are_complete(self) -> None:
        for technique, value in self.result["techniques"].items():
            exact = value["exact_restoration"]
            with self.subTest(technique=technique):
                self.assertEqual(exact["all_variants"], exact["all_total"])
                self.assertEqual(exact["changed_variants"], exact["changed_total"])

    def test_records_historical_jamo_generator_limitation(self) -> None:
        limitations = " ".join(self.result["limitations"])

        self.assertIn("jamo_decompose", limitations)
        self.assertIn("current generator", limitations)


if __name__ == "__main__":
    unittest.main()
