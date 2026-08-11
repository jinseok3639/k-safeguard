import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from experiments.benchmark.adapters import AdapterResult
from experiments.benchmark.run_tensify_benign_dev_evaluation import (
    DEFAULT_BASELINE,
    DEFAULT_INPUT,
    BenignDevRow,
    build_baseline,
    build_policy_plan,
    build_record,
    collect_unique_texts,
    dataset_profile,
    load_benign_dev,
    make_gateways,
    normalized_run_id,
    summarize_policies,
    summarize_transitions,
)
from experiments.benchmark.run_clean_baseline import sha256_file


def payload_sha256(path: Path) -> str:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = [
            {key: value for key, value in row.items() if key != "review_status"}
            for row in csv.DictReader(stream)
        ]
    payload = json.dumps(
        rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def adapter_result(block: bool) -> AdapterResult:
    return AdapterResult(
        block=block,
        category="A1" if block else None,
        raw_output="<UNSAFE-A1>" if block else "<SAFE>",
        error_type=None,
        latency_ms=1.0,
        input_token_count=2,
        tokenized_input_sha256="hash",
        generated_token_id=1,
    )


def row(text: str = "진짜 좋아") -> BenignDevRow:
    return BenignDevRow(
        sample_id="sample",
        subtype="chat",
        text=text,
        source="team",
        review_status="team_review_needed",
        selection_reason="test",
        tense_syllables=2,
        hangul_syllables=4,
        tense_ratio=0.5,
    )


class TensifyBenignDevEvaluationTest(unittest.TestCase):
    def test_repository_dataset_has_expected_scope_and_provenance(self) -> None:
        rows = load_benign_dev(DEFAULT_INPUT)
        profile = dataset_profile(rows)

        self.assertEqual(len(rows), 64)
        self.assertEqual(profile["subtypes"], {
            "colloquial_chat": 16,
            "everyday_lexical": 16,
            "mixed_format": 16,
            "technical_meta": 16,
        })
        self.assertEqual(profile["review_statuses"], {"selected": 64})
        self.assertGreater(profile["ratio_bands"].get("below_0.10", 0), 0)
        self.assertGreater(profile["ratio_bands"].get("at_or_above_0.10", 0), 0)

    def test_loader_rejects_duplicate_text_and_missing_tense(self) -> None:
        header = "sample_id,subtype,text,source,review_status,selection_reason\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dev.csv"
            path.write_text(
                header
                + "a,chat,진짜 좋아,team,pending,test\n"
                + "b,chat,진짜 좋아,team,pending,test\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "중복 text"):
                load_benign_dev(path)

            path.write_text(
                header + "a,chat,오늘 좋아,team,pending,test\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "된소리 음절"):
                load_benign_dev(path)

            path.write_text(
                header + "a,chat,진짜 좋아,team,pending,test,extra\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "헤더보다 많은"):
                load_benign_dev(path)

    def test_ratio_policy_only_activates_at_threshold(self) -> None:
        gateways = make_gateways(max_views=10, max_candidates=9)
        below = "오늘은 꽃이 공원 한가운데 피었습니다"
        above = "진짜 좋아"

        all_plan = build_policy_plan(below, "all", gateways["all"])
        below_plan = build_policy_plan(below, "ratio_0.10", gateways["ratio_0.10"])
        above_plan = build_policy_plan(above, "ratio_0.10", gateways["ratio_0.10"])

        self.assertTrue(all_plan.activated)
        self.assertFalse(below_plan.activated)
        self.assertTrue(above_plan.activated)

    def test_unique_texts_preserve_first_seen_order(self) -> None:
        gateways = make_gateways(max_views=10, max_candidates=9)
        raw = build_policy_plan("진짜 좋아", "raw", gateways["raw"])
        expanded = build_policy_plan("진짜 좋아", "all", gateways["all"])

        self.assertEqual(collect_unique_texts([raw, expanded])[0], "진짜 좋아")
        self.assertEqual(len(collect_unique_texts([raw, expanded])), len(expanded.texts))

    def test_metrics_compare_each_policy_with_raw(self) -> None:
        gateways = make_gateways(max_views=10, max_candidates=9)
        fixture_row = row()
        blocks = {"raw": False, "all": True, "ratio_0.10": False}
        records = []
        for policy, block in blocks.items():
            plan = build_policy_plan(fixture_row.text, policy, gateways[policy])
            records.append(
                build_record(
                    fixture_row,
                    plan,
                    [adapter_result(block)] * len(plan.texts),
                )
            )

        metrics = summarize_policies(records, 0, 2026)
        transitions = summarize_transitions(records)

        self.assertEqual(metrics["all"]["metrics"]["fpr"]["seed_balanced_estimate"], 1.0)
        self.assertEqual(metrics["all"]["metrics"]["delta_fpr"]["seed_balanced_estimate"], 1.0)
        self.assertEqual(metrics["ratio_0.10"]["metrics"]["delta_fpr"]["seed_balanced_estimate"], 0.0)
        self.assertEqual(transitions["all"]["newly_blocked"], 1)
        self.assertEqual(transitions["ratio_0.10"]["unchanged"], 1)

    def test_baseline_uses_portable_dataset_path(self) -> None:
        summary = {"status": "PROVISIONAL_DEV_ONLY"}
        manifest = {
            "run_id": "run",
            "created_at": "2026-08-11T00:00:00+00:00",
            "spec_version": "0.1.0",
            "git": {"commit": "abc", "dirty": False},
            "dataset": {"path": str(DEFAULT_INPUT), "sha256": "data"},
            "model": {
                "model_id": "model",
                "revision": "revision",
                "dtype": "float16",
                "gpu_name": "gpu",
            },
            "candidate_generator": {"version": "0.2.0"},
            "runtime": {"bootstrap_samples": 0, "random_seed": 1, "batch_size": 2},
        }

        baseline = build_baseline(summary, manifest)

        self.assertEqual(
            baseline["provenance"]["input"]["path"],
            "experiments/benchmark/data/tensify_benign_dev_v1.csv",
        )

    def test_repository_baseline_matches_dataset_and_expected_result(self) -> None:
        baseline = json.loads(DEFAULT_BASELINE.read_text(encoding="utf-8"))
        review = json.loads(
            (
                DEFAULT_BASELINE.parent / "tensify_human_review_v1.json"
            ).read_text(encoding="utf-8")
        )
        metrics = baseline["policy_metrics"]

        self.assertEqual(baseline["status"], "PROVISIONAL_DEV_ONLY")
        self.assertFalse(baseline["provenance"]["git"]["dirty"])
        self.assertEqual(
            baseline["provenance"]["input"]["sha256"],
            review["datasets"]["benign_dev"]["before_review_sha256"],
        )
        self.assertEqual(
            review["datasets"]["benign_dev"]["after_review_sha256"],
            sha256_file(DEFAULT_INPUT),
        )
        self.assertEqual(
            review["datasets"]["benign_dev"][
                "payload_without_review_status_sha256"
            ],
            payload_sha256(DEFAULT_INPUT),
        )
        self.assertEqual(
            metrics["raw"]["metrics"]["fpr"]["seed_balanced_estimate"], 9 / 64
        )
        self.assertEqual(
            metrics["all"]["metrics"]["delta_fpr"]["seed_balanced_estimate"], 0.0
        )
        self.assertEqual(
            metrics["ratio_0.10"]["metrics"]["activation_rate"][
                "seed_balanced_estimate"
            ],
            26 / 64,
        )
        self.assertEqual(baseline["view_errors"], 0)

    def test_run_id_rejects_path_characters(self) -> None:
        self.assertEqual(normalized_run_id("valid-run_1"), "valid-run_1")
        with self.assertRaisesRegex(ValueError, "run-id"):
            normalized_run_id("../invalid")


if __name__ == "__main__":
    unittest.main()
