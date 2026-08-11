import unittest
from dataclasses import replace

from experiments.benchmark.run_chosung_lexical_diagnostic import (
    DiagnosticObservation,
    OUTCOME_CANDIDATE_NOT_GENERATED,
    OUTCOME_OVER_RESTORATION,
    OUTCOME_RANKING_ERROR,
    OUTCOME_SUCCESS,
    OUTCOME_TARGET_NOT_IN_CANDIDATES,
    classify_observation,
    observe_row,
    outcome_examples,
    summarize,
    summarize_outcomes,
)
from k_safeguard.chosung import ChosungLexicon


class ChosungDiagnosticTest(unittest.TestCase):
    def test_observes_exact_candidate_without_using_original_as_lexicon(self) -> None:
        lexicon = ChosungLexicon(["시스템", "산사태"])
        observation = observe_row(
            "ㅅㅅㅌ 점검",
            "시스템 점검",
            "benign",
            "benign_hard_negative",
            1.0,
            lexicon,
            min_initials=3,
            max_options_per_span=3,
            max_candidates=8,
        )
        self.assertTrue(observation.generated)
        self.assertTrue(observation.exact_hit)
        self.assertTrue(observation.top1_exact)
        self.assertEqual(observation.best_initial_recall, 1.0)

    def test_summarizes_rates(self) -> None:
        rows = [
            DiagnosticObservation("attack", "A1", 1.0, True, 2, True, True, 3, 1.0, False),
            DiagnosticObservation("benign", "benign", 1.0, False, 0, False, False, 3, 0.0, False),
        ]
        result = summarize(rows)
        self.assertEqual(result["overall"]["rows"], 2)
        self.assertEqual(result["overall"]["candidate_generation_rate"], 0.5)
        self.assertEqual(result["overall"]["exact_hit_rate"], 0.5)
        self.assertIn("label:attack", result)

    def test_classifies_mutually_exclusive_error_taxonomy(self) -> None:
        base = DiagnosticObservation(
            "attack", "A1", 1.0, False, 0, False, False, 3, 0.0, False
        )

        self.assertEqual(
            classify_observation(base),
            OUTCOME_CANDIDATE_NOT_GENERATED,
        )
        self.assertEqual(
            classify_observation(replace(base, generated=True, candidate_count=2)),
            OUTCOME_OVER_RESTORATION,
        )
        self.assertEqual(
            classify_observation(
                replace(base, generated=True, candidate_count=2, best_initial_recall=0.5)
            ),
            OUTCOME_TARGET_NOT_IN_CANDIDATES,
        )
        self.assertEqual(
            classify_observation(
                replace(base, generated=True, candidate_count=2, exact_hit=True)
            ),
            OUTCOME_RANKING_ERROR,
        )
        self.assertEqual(
            classify_observation(
                replace(
                    base,
                    generated=True,
                    candidate_count=2,
                    exact_hit=True,
                    top1_exact=True,
                )
            ),
            OUTCOME_SUCCESS,
        )

    def test_summarizes_outcomes_and_keeps_traceable_examples(self) -> None:
        rows = [
            DiagnosticObservation(
                "attack",
                "A1",
                1.0,
                False,
                0,
                False,
                False,
                3,
                0.0,
                False,
                "variant-1",
                "seed-1",
            ),
            DiagnosticObservation(
                "benign",
                "benign",
                0.5,
                True,
                2,
                False,
                False,
                3,
                0.5,
                True,
                "variant-2",
                "seed-2",
            ),
        ]

        summary = summarize_outcomes(rows)
        self.assertEqual(summary["overall"]["rows"], 2)
        self.assertEqual(
            summary["overall"]["counts"][OUTCOME_CANDIDATE_NOT_GENERATED],
            1,
        )
        self.assertEqual(
            summary["overall"]["counts"][OUTCOME_TARGET_NOT_IN_CANDIDATES],
            1,
        )
        self.assertIn("category:A1", summary)

        examples = outcome_examples(rows, limit_per_outcome=1)
        self.assertEqual(
            examples[OUTCOME_CANDIDATE_NOT_GENERATED][0]["row_id"],
            "variant-1",
        )


if __name__ == "__main__":
    unittest.main()
