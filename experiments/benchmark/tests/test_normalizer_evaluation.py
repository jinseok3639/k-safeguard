import json
import tempfile
import unittest
from pathlib import Path

from experiments.benchmark.run_normalizer_evaluation import (
    BenchmarkRow,
    build_condition_tasks,
    build_variant_pairs,
    clean_gateway_metrics,
    gateway_metrics,
    load_benchmark,
    summarize_observations,
    summarize_run,
)


def result_record(
    *,
    condition: str,
    seed_id: str,
    variant_id: str,
    label: str,
    block: bool,
    changed: bool = True,
    technique: str = "jamo_decompose",
    category: str = "A1",
    normalized_changed: bool | None = None,
    exact: bool | None = None,
) -> dict:
    return {
        "condition": condition,
        "seed_id": seed_id,
        "variant_id": variant_id,
        "label": label,
        "category": category,
        "family": "visual" if technique != "clean" else "clean",
        "technique": technique,
        "intensity": 1.0 if technique != "clean" else 0.0,
        "changed": changed,
        "gateway_enabled": condition in {"E2", "E3"},
        "normalizer_changed": normalized_changed,
        "normalizer_exact_restoration": exact,
        "normalizer_latency_ms": 0.1,
        "guardrail_block": block,
        "error_type": None,
        "latency_ms": 1.0,
    }


class BenchmarkLoaderTest(unittest.TestCase):
    def test_loads_and_filters_complete_seed_pairs(self) -> None:
        rows = [
            {
                "id": "clean-1",
                "seed_id": "seed-1",
                "original": "안녕",
                "text": "안녕",
                "label": "attack",
                "category": "A1_injection",
                "technique": "clean",
                "intensity": 0,
            },
            {
                "id": "obf-1",
                "seed_id": "seed-1",
                "original": "안녕",
                "text": "ㅇㅏㄴㄴㅕㅇ",
                "label": "attack",
                "category": "A1_injection",
                "technique": "jamo_decompose",
                "intensity": 1,
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "benchmark.jsonl"
            path.write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
                encoding="utf-8",
            )
            loaded = load_benchmark(path, techniques={"jamo_decompose"})
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[1].category, "A1_injection")

    def test_rejects_seed_without_exactly_one_clean_row(self) -> None:
        row = {
            "id": "obf-1",
            "seed_id": "seed-1",
            "original": "안녕",
            "text": "ㅇㅏㄴㄴㅕㅇ",
            "label": "attack",
            "category": "A1_injection",
            "technique": "jamo_decompose",
            "intensity": 1,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "benchmark.jsonl"
            path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "clean 행"):
                load_benchmark(path)


class TaskBuilderTest(unittest.TestCase):
    def test_builds_four_conditions_and_normalizes_gateway_inputs(self) -> None:
        clean = BenchmarkRow(
            "clean", "seed", "안녕", "안녕", "attack", "A1_injection", "clean", 0.0
        )
        obfuscated = BenchmarkRow(
            "obf",
            "seed",
            "안녕",
            "ㅇㅏㄴㄴㅕㅇ",
            "attack",
            "A1_injection",
            "jamo_decompose",
            1.0,
        )
        tasks = build_condition_tasks([clean, obfuscated])
        self.assertEqual([task.condition for task in tasks], ["E0", "E3", "E1", "E2"])
        e2 = tasks[-1]
        self.assertEqual(e2.inference_text, "안녕")
        self.assertTrue(e2.normalization.changed)


class MetricTest(unittest.TestCase):
    def test_seed_balanced_estimate_does_not_overweight_more_rows(self) -> None:
        metric = summarize_observations(
            [("seed-a", 1.0), ("seed-a", 1.0), ("seed-b", 0.0)],
            bootstrap_samples=0,
            random_seed=2026,
        )
        self.assertAlmostEqual(metric["micro_estimate"], 2 / 3)
        self.assertAlmostEqual(metric["seed_balanced_estimate"], 0.5)

    def test_gateway_metrics_separate_evasion_and_recovery(self) -> None:
        records = [
            result_record(
                condition="E0", seed_id="attack", variant_id="clean-a", label="attack", block=True,
                technique="clean", changed=False,
            ),
            result_record(
                condition="E1", seed_id="attack", variant_id="obf-a", label="attack", block=False,
            ),
            result_record(
                condition="E2", seed_id="attack", variant_id="obf-a", label="attack", block=True,
                normalized_changed=True, exact=True,
            ),
        ]
        pairs = build_variant_pairs(records)
        metrics = gateway_metrics(pairs, bootstrap_samples=0, random_seed=2026)
        self.assertEqual(metrics["cer"]["seed_balanced_estimate"], 1.0)
        self.assertEqual(metrics["residual_cer"]["seed_balanced_estimate"], 0.0)
        self.assertEqual(metrics["nrr"]["seed_balanced_estimate"], 1.0)
        self.assertEqual(metrics["recovery_gain"]["seed_balanced_estimate"], 1.0)

    def test_clean_metrics_measure_mutation_and_benign_fpr_delta(self) -> None:
        records = [
            result_record(
                condition="E0", seed_id="benign", variant_id="clean-b", label="benign", block=False,
                technique="clean", category="benign_hard_negative", changed=False,
            ),
            result_record(
                condition="E3", seed_id="benign", variant_id="clean-b", label="benign", block=False,
                technique="clean", category="benign_hard_negative", changed=False,
                normalized_changed=False, exact=True,
            ),
        ]
        metrics = clean_gateway_metrics(records, bootstrap_samples=0, random_seed=2026)
        self.assertEqual(metrics["clean_mutation_rate"]["seed_balanced_estimate"], 0.0)
        self.assertEqual(metrics["delta_fpr_clean"]["seed_balanced_estimate"], 0.0)

    def test_summary_stays_incomplete_without_comprehension(self) -> None:
        records = [
            result_record(
                condition="E0", seed_id="attack", variant_id="clean-a", label="attack", block=True,
                technique="clean", changed=False,
            ),
            result_record(
                condition="E3", seed_id="attack", variant_id="clean-a", label="attack", block=True,
                technique="clean", changed=False, normalized_changed=False, exact=True,
            ),
            result_record(
                condition="E1", seed_id="attack", variant_id="obf-a", label="attack", block=False,
            ),
            result_record(
                condition="E2", seed_id="attack", variant_id="obf-a", label="attack", block=True,
                normalized_changed=True, exact=True,
            ),
        ]
        summary = summarize_run(records, bootstrap_samples=0, random_seed=2026)
        self.assertEqual(summary["validity"], "INCOMPLETE")
        self.assertEqual(summary["decision"], "NOT_EVALUATED")
        self.assertFalse(
            summary["validity_checks"]["clean_intent_recognition_at_least_90pct"]
        )


if __name__ == "__main__":
    unittest.main()
