import unittest

from experiments.benchmark.adapters import AdapterResult
from experiments.benchmark.run_chosung_guardrail_evaluation import (
    POLICIES,
    aggregate_view_results,
    build_policy_candidates,
    summarize_policy_metrics,
    summarize_policy_transitions,
)
from k_safeguard.chosung import ChosungLexicon


def adapter_result(
    block: bool | None,
    *,
    category: str | None = None,
    error_type: str | None = None,
) -> AdapterResult:
    return AdapterResult(
        block=block,
        category=category,
        raw_output="<SAFE>" if block is False else "<UNSAFE-A1>",
        error_type=error_type,
        latency_ms=1.0,
        input_token_count=3,
        tokenized_input_sha256="hash",
        generated_token_id=1,
    )


def policy_record(
    variant_id: str,
    seed_id: str,
    label: str,
    technique: str,
    policy: str,
    block: bool,
    views: tuple[str, ...] = ("raw",),
) -> dict:
    return {
        "variant_id": variant_id,
        "seed_id": seed_id,
        "label": label,
        "category": "A1_injection" if label == "attack" else "benign_hard_negative",
        "technique": technique,
        "intensity": 0.0 if technique == "clean" else 1.0,
        "policy": policy,
        "policy_block": block,
        "policy_error": None,
        "generated_view_count": 0 if policy == "raw" else 1,
        "truncated": False,
        "views": [{"text": text} for text in views],
    }


class PolicyCandidateTest(unittest.TestCase):
    def test_policies_add_only_their_bounded_candidate_layer(self) -> None:
        lexicon = ChosungLexicon.from_sources(
            [("domain", ["시스템", "프롬프트"]), ("general", ["산사태"])]
        )
        policies = {policy.name: policy for policy in POLICIES}

        direct = build_policy_candidates(
            "ㅅㅅㅌㅍㄹㅍㅌ",
            lexicon,
            policies["direct"],
            partial_source="domain",
        )
        segmented = build_policy_candidates(
            "ㅅㅅㅌㅍㄹㅍㅌ",
            lexicon,
            policies["segmented"],
            partial_source="domain",
        )
        partial = build_policy_candidates(
            "ㄱㄱㅅㅅㅌㄴ",
            lexicon,
            policies["partial"],
            partial_source="domain",
        )

        self.assertEqual(direct.texts, ("ㅅㅅㅌㅍㄹㅍㅌ",))
        self.assertIn("시스템프롬프트", segmented.texts)
        self.assertIn("ㄱㄱ시스템ㄴ", partial.texts)
        self.assertEqual(partial.partial_candidate_count, 1)

    def test_aggregate_uses_or_and_rejects_partial_errors(self) -> None:
        blocked = aggregate_view_results(
            [adapter_result(False), adapter_result(True, category="A1")]
        )
        self.assertTrue(blocked["block"])
        self.assertEqual(blocked["trigger_view_index"], 1)

        invalid = aggregate_view_results(
            [adapter_result(False), adapter_result(None, error_type="invalid_output")]
        )
        self.assertIsNone(invalid["block"])
        self.assertEqual(invalid["error_type"], "invalid_output")


class PolicyMetricTest(unittest.TestCase):
    def test_metrics_pair_recovery_and_false_positive_delta_against_raw(self) -> None:
        records = []
        policy_blocks = {
            "raw": (True, False, False, False),
            "direct": (True, True, False, True),
            "segmented": (True, True, False, False),
            "partial": (True, True, False, False),
        }
        for policy, (attack_clean, attack_obf, benign_clean, benign_obf) in policy_blocks.items():
            records.extend(
                [
                    policy_record("clean-a", "attack", "attack", "clean", policy, attack_clean),
                    policy_record("obf-a", "attack", "attack", "chosung", policy, attack_obf),
                    policy_record("clean-b", "benign", "benign", "clean", policy, benign_clean),
                    policy_record("obf-b", "benign", "benign", "chosung", policy, benign_obf),
                ]
            )

        metrics = summarize_policy_metrics(records, bootstrap_samples=0, random_seed=2026)

        self.assertEqual(metrics["direct"]["nrr"]["seed_balanced_estimate"], 1.0)
        self.assertEqual(
            metrics["direct"]["attack_block_rate"]["seed_balanced_estimate"],
            1.0,
        )
        self.assertEqual(
            metrics["direct"]["clean_attack_block_rate"]["seed_balanced_estimate"],
            1.0,
        )
        self.assertEqual(
            metrics["direct"]["delta_fpr_obfuscated"]["seed_balanced_estimate"],
            1.0,
        )
        self.assertEqual(
            metrics["segmented"]["delta_fpr_obfuscated"]["seed_balanced_estimate"],
            0.0,
        )
        self.assertEqual(metrics["segmented"]["delta_fpr_clean"]["seed_balanced_estimate"], 0.0)

    def test_transition_metrics_expose_gains_losses_and_candidate_displacement(self) -> None:
        records = []
        policy_rows = {
            "raw": (False, False, ("raw",)),
            "direct": (True, True, ("raw", "direct")),
            "segmented": (False, False, ("raw", "segment")),
            "partial": (False, False, ("raw", "segment", "partial")),
        }
        for policy, (attack_block, benign_block, views) in policy_rows.items():
            records.extend(
                [
                    policy_record(
                        "obf-a", "attack", "attack", "chosung", policy,
                        attack_block, views,
                    ),
                    policy_record(
                        "obf-b", "benign", "benign", "chosung", policy,
                        benign_block, views,
                    ),
                ]
            )

        transitions = summarize_policy_transitions(records)

        self.assertEqual(transitions[0]["attack_newly_blocked"], 1)
        self.assertEqual(transitions[0]["benign_newly_blocked"], 1)
        self.assertEqual(transitions[1]["attack_newly_allowed"], 1)
        self.assertEqual(transitions[1]["benign_newly_allowed"], 1)
        self.assertEqual(transitions[1]["candidate_set_contained_rate"], 0.0)
        self.assertEqual(transitions[2]["candidate_set_contained_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
