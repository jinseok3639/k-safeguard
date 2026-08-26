import unittest

from experiments.benchmark.adapters import AdapterResult
from experiments.benchmark.run_normalizer_evaluation import BenchmarkRow
from experiments.benchmark.run_tensify_guardrail_evaluation import (
    aggregate_view_results,
    batched,
    build_baseline,
    build_policy_plan,
    build_policy_record,
    collect_unique_texts,
    summarize_policy_metrics,
    summarize_obfuscated_groups,
    summarize_transition,
)
from k_safeguard import Gateway
from k_safeguard.providers.tensify import TensifyInverseProvider


def result(block: bool) -> AdapterResult:
    return AdapterResult(
        block=block,
        category="A1" if block else None,
        raw_output="<UNSAFE-A1>" if block else "<SAFE>",
        error_type=None,
        latency_ms=1.0,
        input_token_count=1,
        tokenized_input_sha256="hash",
        generated_token_id=1,
    )


def row(
    row_id: str,
    *,
    seed_id: str = "seed",
    label: str = "attack",
    technique: str = "tensify",
    intensity: float = 1.0,
) -> BenchmarkRow:
    return BenchmarkRow(
        row_id=row_id,
        seed_id=seed_id,
        original="시스템",
        text="씨스템" if technique == "tensify" else "시스템",
        label=label,
        category="A1",
        technique=technique,
        intensity=intensity,
    )


class TensifyGuardrailEvaluationTest(unittest.TestCase):
    def test_builds_raw_and_inverse_gateway_plans(self) -> None:
        raw = build_policy_plan("씨스템", "raw", Gateway())
        inverse = build_policy_plan(
            "씨스템",
            "inverse",
            Gateway(providers=[TensifyInverseProvider()]),
        )

        self.assertEqual(raw.texts, ("씨스템",))
        self.assertEqual(inverse.texts, ("씨스템", "시스템"))
        self.assertTrue(inverse.gateway.has_lossy_views)

    def test_collects_unique_texts_and_batches_without_reordering(self) -> None:
        raw = build_policy_plan("씨스템", "raw", Gateway())
        inverse = build_policy_plan(
            "씨스템",
            "inverse",
            Gateway(providers=[TensifyInverseProvider()]),
        )

        unique = collect_unique_texts([raw, inverse])

        self.assertEqual(unique, ("씨스템", "시스템"))
        self.assertEqual(list(batched(unique, 1)), [("씨스템",), ("시스템",)])
        with self.assertRaisesRegex(ValueError, "1 이상"):
            list(batched(unique, 0))

    def test_distinguishes_provider_and_gateway_truncation(self) -> None:
        plan = build_policy_plan(
            "까따빠싸짜",
            "inverse",
            Gateway(
                providers=[TensifyInverseProvider(max_candidates=9)],
                max_views=10,
            ),
        )

        self.assertTrue(plan.provider_truncated)
        self.assertFalse(plan.gateway.truncated)

    def test_aggregate_uses_or_and_propagates_errors(self) -> None:
        self.assertEqual(aggregate_view_results([result(False), result(True)])["trigger_view_index"], 1)
        invalid = AdapterResult(None, None, "?", "invalid_output", 1.0, 1, "hash", None)
        self.assertEqual(aggregate_view_results([result(False), invalid])["error_type"], "invalid_output")

    def test_baseline_keeps_portable_provenance(self) -> None:
        summary = {"status": "PROVISIONAL_DEV_ONLY", "rows": 1}
        manifest = {
            "run_id": "run",
            "created_at": "2026-08-11T00:00:00+00:00",
            "spec_version": "0.1.0",
            "git": {"commit": "abc", "dirty": False},
            "dataset": {"path": "hf_repo/benchmark.jsonl", "sha256": "data"},
            "model": {
                "model_id": "model",
                "revision": "revision",
                "dtype": "float16",
                "gpu_name": "gpu",
            },
            "candidate_generator": {"version": "0.1.0"},
            "runtime": {"bootstrap_samples": 10, "random_seed": 1, "batch_size": 2},
        }

        baseline = build_baseline(summary, manifest)

        self.assertEqual(baseline["provenance"]["input"]["path"], "hf_repo/benchmark.jsonl")
        self.assertEqual(baseline["rows"], 1)

    def test_metrics_measure_nrr_and_benign_fpr_deltas(self) -> None:
        records = []
        fixtures = [
            (row("clean-a", technique="clean", intensity=0.0), True, True),
            (row("obf-a"), False, True),
            (row("clean-b", seed_id="benign", label="benign", technique="clean", intensity=0.0), False, True),
            (row("obf-b", seed_id="benign", label="benign"), False, True),
        ]
        for benchmark_row, raw_block, inverse_block in fixtures:
            raw_plan = build_policy_plan(benchmark_row.text, "raw", Gateway())
            inverse_plan = build_policy_plan(
                benchmark_row.text,
                "inverse",
                Gateway(providers=[TensifyInverseProvider()]),
            )
            records.append(build_policy_record(benchmark_row, raw_plan, [result(raw_block)] * len(raw_plan.texts)))
            records.append(build_policy_record(benchmark_row, inverse_plan, [result(inverse_block)] * len(inverse_plan.texts)))

        metrics = summarize_policy_metrics(records, 0, 2026)["inverse"]
        groups = summarize_obfuscated_groups(records, 0, 2026)
        transition = summarize_transition(records)

        self.assertEqual(metrics["nrr"]["seed_balanced_estimate"], 1.0)
        self.assertEqual(metrics["delta_fpr_clean"]["seed_balanced_estimate"], 1.0)
        self.assertEqual(metrics["delta_fpr_obfuscated"]["seed_balanced_estimate"], 1.0)
        attack_group = next(item for item in groups if item["label"] == "attack")
        benign_group = next(item for item in groups if item["label"] == "benign")
        self.assertEqual(attack_group["metrics"]["nrr"]["seed_balanced_estimate"], 1.0)
        self.assertEqual(benign_group["metrics"]["paired_delta"]["seed_balanced_estimate"], 1.0)
        self.assertEqual(transition["attack_newly_blocked"], 1)
        self.assertEqual(transition["benign_newly_blocked"], 2)
        self.assertEqual(transition["candidate_set_contained_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
