import unittest

from experiments.benchmark.run_chosung_runtime_smoke import (
    DEFAULT_VARIANT_IDS,
    build_record,
    contract_exit_code,
    select_chosung_rows,
    summarize,
)
from experiments.benchmark.run_normalizer_evaluation import (
    DEFAULT_INPUT,
    BenchmarkRow,
    load_benchmark,
)
from k_safeguard import CandidateProposal, Gateway


class _ManyCandidateProvider:
    name = "many"

    def generate(self, text: str):
        for index in range(12):
            yield CandidateProposal(f"후보-{index}")


def row(
    row_id: str,
    *,
    technique: str = "chosung",
    label: str = "attack",
    category: str = "A1_injection",
) -> BenchmarkRow:
    return BenchmarkRow(
        row_id=row_id,
        seed_id="seed",
        original="원문",
        text="ㅇㅁ",
        label=label,
        category=category,
        technique=technique,
        intensity=1.0,
    )


class ChosungRuntimeSmokeTest(unittest.TestCase):
    def test_default_fixtures_exist_and_cover_a1_a2(self) -> None:
        selected = select_chosung_rows(load_benchmark(DEFAULT_INPUT), DEFAULT_VARIANT_IDS)

        self.assertEqual(len(selected), 2)
        self.assertEqual({item.category for item in selected}, {"A1_injection", "A2_leaking"})

    def test_rejects_invalid_fixture_selection(self) -> None:
        rows = [row("valid")]
        with self.assertRaisesRegex(ValueError, "없습니다"):
            select_chosung_rows(rows, ["missing"])
        with self.assertRaisesRegex(ValueError, "중복"):
            select_chosung_rows(rows, ["valid", "valid"])
        with self.assertRaisesRegex(ValueError, "chosung"):
            select_chosung_rows(rows + [row("jamo", technique="jamo_decompose")], ["jamo"])
        with self.assertRaisesRegex(ValueError, "A1/A2"):
            select_chosung_rows(
                rows + [
                    row(
                        "benign",
                        label="benign",
                        category="benign_hard_negative",
                    )
                ],
                ["benign"],
            )

    def test_short_circuit_preserves_decision_and_saves_model_calls(self) -> None:
        gateway = Gateway(providers=[_ManyCandidateProvider()], max_views=10)

        def classifier(text: str) -> bool:
            return text == "후보-0"

        full = gateway.evaluate("ㅇㅁ", classifier, stop_on_block=False)
        short = gateway.evaluate("ㅇㅁ", classifier, stop_on_block=True)
        record = build_record(row("fixture"), full, short)
        summary = summarize([record])

        self.assertEqual(record["configured_views"], 10)
        self.assertEqual(record["full_model_calls"], 10)
        self.assertEqual(record["short_model_calls"], 2)
        self.assertEqual(record["model_calls_saved"], 8)
        self.assertEqual(record["model_call_reduction"], 0.8)
        self.assertTrue(record["same_view_plan"])
        self.assertTrue(record["same_decision"])
        self.assertTrue(record["recovered"])
        self.assertEqual(summary["model_call_reduction"], 0.8)
        self.assertEqual(contract_exit_code(summary, True), 0)

    def test_contract_gate_distinguishes_regression_and_errors(self) -> None:
        partial = {
            "fixtures": 2,
            "recoveries": 1,
            "same_decisions": 2,
            "same_view_plans": 2,
            "short_circuited": 2,
            "model_calls_saved": 1,
            "errors": 0,
        }
        errored = dict(partial, errors=1)

        self.assertEqual(contract_exit_code(partial, True), 1)
        self.assertEqual(contract_exit_code(partial, False), 0)
        self.assertEqual(contract_exit_code(errored, True), 2)


if __name__ == "__main__":
    unittest.main()
