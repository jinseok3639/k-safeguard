import unittest

from experiments.benchmark.run_kanana_batch_benchmark import (
    benchmark_exit_code,
    evaluation_signature,
    normalized_batch_sizes,
    normalized_run_id,
    rotated_modes,
    summarize_measurements,
)
from k_safeguard import CandidateProposal, Gateway


class _ViewsProvider:
    name = "views"

    def generate(self, text: str):
        yield CandidateProposal(text + "-1")
        yield CandidateProposal(text + "-2")


class KananaBatchBenchmarkContractTest(unittest.TestCase):
    def test_normalizes_unique_sorted_batch_sizes(self) -> None:
        self.assertEqual(normalized_batch_sizes([4, 2, 4], 10), (2, 4))
        self.assertEqual(normalized_batch_sizes(None, 10), (2, 4, 10))
        with self.assertRaisesRegex(ValueError, "1 이상"):
            normalized_batch_sizes([0], 10)
        with self.assertRaisesRegex(TypeError, "int"):
            normalized_batch_sizes([True], 10)

    def test_rotates_mode_order_by_repeat(self) -> None:
        modes = (("single", None), ("batch", 2), ("batch", 4))
        self.assertEqual(rotated_modes(modes, 0), modes)
        self.assertEqual(
            rotated_modes(modes, 1),
            (("batch", 2), ("batch", 4), ("single", None)),
        )

    def test_single_and_batch_signatures_match_for_same_outputs(self) -> None:
        gateway = Gateway(providers=[_ViewsProvider()])
        single = gateway.evaluate(
            "입력",
            lambda text: text.endswith("-1"),
            stop_on_block=False,
        )
        batch = gateway.evaluate_batch(
            "입력",
            lambda texts: [text.endswith("-1") for text in texts],
            batch_size=2,
            stop_on_block=False,
        )

        self.assertEqual(evaluation_signature(single), evaluation_signature(batch))

    def test_summarizes_speed_call_reduction_memory_and_parity(self) -> None:
        def record(
            mode_key: str,
            batch_size: int,
            wall: float,
            calls: int,
            throughput: float,
            memory: float,
            parity: bool = True,
        ):
            return {
                "mode_key": mode_key,
                "batch_size": batch_size,
                "evaluated_views": 20,
                "classifier_calls": calls,
                "wall_time_ms": wall,
                "classifier_latency_sum_ms": wall - 1,
                "views_per_second": throughput,
                "incremental_peak_allocated_mib": memory,
                "incremental_peak_reserved_mib": memory + 10,
                "decision_parity": parity,
                "classifier_errors": 0,
            }

        summary = summarize_measurements(
            [
                record("single", 1, 100, 20, 200, 100),
                record("single", 1, 120, 20, 180, 110),
                record("batch_4", 4, 50, 6, 400, 200),
                record("batch_4", 4, 60, 6, 360, 220),
            ]
        )

        batch = summary["modes"]["batch_4"]
        self.assertEqual(batch["wall_time_median_ms"], 55)
        self.assertEqual(batch["speedup_vs_single"], 2)
        self.assertEqual(batch["call_reduction_vs_single"], 0.7)
        self.assertEqual(batch["incremental_peak_allocated_median_mib"], 210)
        self.assertTrue(summary["all_decisions_match_single"])

    def test_exit_code_distinguishes_error_and_parity_failure(self) -> None:
        valid = {"classifier_errors": 0, "all_decisions_match_single": True}
        self.assertEqual(benchmark_exit_code(valid, True), 0)
        self.assertEqual(
            benchmark_exit_code(
                {"classifier_errors": 0, "all_decisions_match_single": False},
                True,
            ),
            1,
        )
        self.assertEqual(
            benchmark_exit_code(
                {"classifier_errors": 1, "all_decisions_match_single": True},
                False,
            ),
            2,
        )

    def test_rejects_unsafe_run_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "run ID"):
            normalized_run_id("../escape")


if __name__ == "__main__":
    unittest.main()
