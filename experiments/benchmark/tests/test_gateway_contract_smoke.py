import unittest

from experiments.benchmark.run_gateway_contract_smoke import (
    DEFAULT_VARIANT_IDS,
    build_record,
    contract_exit_code,
    select_contract_rows,
    summarize,
)
from experiments.benchmark.run_normalizer_evaluation import (
    DEFAULT_INPUT,
    BenchmarkRow,
    load_benchmark,
)
from k_safeguard import ClassifierResult, Gateway


def row(
    row_id: str,
    seed_id: str,
    technique: str,
    category: str = "A1_injection",
) -> BenchmarkRow:
    original = "원문"
    return BenchmarkRow(
        row_id=row_id,
        seed_id=seed_id,
        original=original,
        text=original if technique == "clean" else "ㅇㅝㄴㅁㅜㄴ",
        label="attack",
        category=category,
        technique=technique,
        intensity=0.0 if technique == "clean" else 1.0,
    )


class GatewayContractSmokeTest(unittest.TestCase):
    def test_default_fixtures_exist_and_cover_a1_a2(self) -> None:
        selected = select_contract_rows(load_benchmark(DEFAULT_INPUT), DEFAULT_VARIANT_IDS)

        self.assertEqual(len(selected), 6)
        self.assertEqual({item.category for item in selected}, {"A1_injection", "A2_leaking"})

    def test_selects_each_seed_clean_pair_before_requested_variants(self) -> None:
        rows = [
            row("clean-a1", "a1", "clean"),
            row("variant-a1-1", "a1", "jamo_decompose"),
            row("variant-a1-2", "a1", "zwsp_inject"),
            row("clean-a2", "a2", "clean", "A2_leaking"),
            row("variant-a2", "a2", "jamo_decompose", "A2_leaking"),
        ]

        selected = select_contract_rows(
            rows,
            ["variant-a1-2", "variant-a1-1", "variant-a2"],
        )

        self.assertEqual(
            [item.row_id for item in selected],
            ["clean-a1", "variant-a1-2", "variant-a1-1", "clean-a2", "variant-a2"],
        )

    def test_rejects_missing_duplicate_clean_and_out_of_scope_variants(self) -> None:
        rows = [
            row("clean", "a1", "clean"),
            row("variant", "a1", "jamo_decompose"),
        ]
        with self.assertRaisesRegex(ValueError, "없습니다"):
            select_contract_rows(rows, ["missing"])
        with self.assertRaisesRegex(ValueError, "중복"):
            select_contract_rows(rows, ["variant", "variant"])
        with self.assertRaisesRegex(ValueError, "clean"):
            select_contract_rows(rows, ["clean"])

        benign = BenchmarkRow(
            row_id="benign",
            seed_id="b",
            original="정상",
            text="정 상",
            label="benign",
            category="benign_hard_negative",
            technique="break_spacing",
            intensity=1.0,
        )
        with self.assertRaisesRegex(ValueError, "A1/A2"):
            select_contract_rows(rows + [benign], ["benign"])

    def test_builds_trace_and_summarizes_normalized_recovery(self) -> None:
        calls = 0

        def classifier(text: str) -> ClassifierResult:
            nonlocal calls
            calls += 1
            return ClassifierResult(
                block=text == "원문",
                category="A1" if text == "원문" else None,
                metadata=(("raw_output", "<UNSAFE-A1>" if text == "원문" else "<SAFE>"),),
            )

        fixture = row("variant", "a1", "jamo_decompose")
        evaluation = Gateway().evaluate(
            fixture.text,
            classifier,
            stop_on_block=False,
        )
        record = build_record(fixture, evaluation)
        summary = summarize([record])

        self.assertEqual(calls, 2)
        self.assertFalse(record["raw_block"])
        self.assertTrue(record["normalized_block"])
        self.assertTrue(record["gateway_block"])
        self.assertEqual(record["trigger_view_kind"], "normalized")
        self.assertTrue(record["recovered"])
        self.assertEqual(summary["recoveries"], 1)
        self.assertEqual(summary["errors"], 0)

    def test_contract_exit_code_requires_all_recoveries_and_no_errors(self) -> None:
        passing = {"errors": 0, "recoveries": 4, "variants": 4}
        partial = {"errors": 0, "recoveries": 3, "variants": 4}
        errored = {"errors": 1, "recoveries": 4, "variants": 4}

        self.assertEqual(contract_exit_code(passing, True), 0)
        self.assertEqual(contract_exit_code(partial, True), 1)
        self.assertEqual(contract_exit_code(partial, False), 0)
        self.assertEqual(contract_exit_code(errored, True), 2)


if __name__ == "__main__":
    unittest.main()
