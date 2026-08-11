import unittest

from experiments.benchmark.run_chosung_lexical_diagnostic import (
    DiagnosticObservation,
    observe_row,
    summarize,
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


if __name__ == "__main__":
    unittest.main()
