import unittest
from itertools import combinations as itertools_combinations
from unittest.mock import patch

from k_safeguard import Gateway
from k_safeguard.providers import (
    TENSIFY_CANDIDATE_VERSION,
    TensifyInverseProvider,
)


class TensifyInverseProviderTest(unittest.TestCase):
    def test_reverses_all_supported_tense_initials(self) -> None:
        # Given
        provider = TensifyInverseProvider(max_candidates=1)
        text = "까따빠싸짜"
        # When
        proposals = list(provider.generate(text))
        # Then
        self.assertEqual([item.text for item in proposals], ["가다바사자"])
        self.assertTrue(proposals[0].lossy)
        self.assertIsNone(proposals[0].confidence)

    def test_preserves_vowels_and_final_consonants(self) -> None:
        # Given
        provider = TensifyInverseProvider()
        text = "꼭 썼다"
        # When
        proposal = next(provider.generate(text))
        # Then
        self.assertEqual(proposal.text, "곡 섰다")

    def test_keeps_full_restore_first_then_single_position_candidates(self) -> None:
        # Given
        provider = TensifyInverseProvider(max_candidates=3)
        text = "까싸"
        # When
        proposals = list(provider.generate(text))
        # Then
        self.assertEqual([item.text for item in proposals], ["가사", "가싸", "까사"])
        self.assertEqual(
            proposals[0].metadata,
            (
                ("replacement_count", "2"),
                ("total_tense_syllables", "2"),
                ("total_hangul_syllables", "2"),
                ("tense_ratio", "1.000000"),
                ("min_tense_syllables", "1"),
                ("min_tense_ratio", "0.000000"),
                ("diversify_from", "17"),
                ("source_positions", "0,1"),
                ("generator_version", TENSIFY_CANDIDATE_VERSION),
            ),
        )

    def test_caps_candidates_deterministically(self) -> None:
        # Given
        provider = TensifyInverseProvider(max_candidates=2)
        text = "까따싸"
        # When
        first = [item.text for item in provider.generate(text)]
        second = [item.text for item in provider.generate(text)]
        # Then
        self.assertEqual(first, second)
        self.assertEqual(first, ["가다사", "가다싸"])

    def test_spreads_long_sentence_budget_across_replacement_counts(self) -> None:
        provider = TensifyInverseProvider(max_candidates=5, diversify_from=5)

        proposals = list(provider.generate("까따빠싸짜"))
        replacement_counts = [
            int(dict(proposal.metadata)["replacement_count"])
            for proposal in proposals
        ]

        self.assertEqual(replacement_counts, [5, 1, 4, 2, 3])

    def test_creates_only_diverse_tier_iterators_that_budget_can_consume(self) -> None:
        provider = TensifyInverseProvider(max_candidates=9)

        with patch(
            "k_safeguard.providers.tensify.combinations",
            wraps=itertools_combinations,
        ) as mocked_combinations:
            proposals = list(provider.generate("까" * 100))

        self.assertEqual(len(proposals), 9)
        self.assertEqual(mocked_combinations.call_count, 8)

    def test_diverse_branch_stops_after_exhausting_all_combinations(self) -> None:
        provider = TensifyInverseProvider(max_candidates=9, diversify_from=2)

        proposals = list(provider.generate("까싸"))

        self.assertEqual(
            [proposal.text for proposal in proposals],
            ["가사", "가싸", "까사"],
        )

    def test_diverse_branch_preserves_mixed_text_and_isolated_jamo(self) -> None:
        provider = TensifyInverseProvider(max_candidates=9)
        text = "까!" * 8 + "API" + "까?" * 9 + " ㄲㅏ🙂"

        proposals = list(provider.generate(text))

        self.assertEqual(proposals[0].text, text.replace("까", "가"))
        self.assertTrue(all("API" in proposal.text for proposal in proposals))
        self.assertTrue(all(proposal.text.endswith(" ㄲㅏ🙂") for proposal in proposals))
        self.assertIn(("total_hangul_syllables", "17"), proposals[0].metadata)

    def test_returns_no_candidate_without_tense_syllable(self) -> None:
        # Given
        provider = TensifyInverseProvider()
        text = "시스템 점검"
        # When
        proposals = list(provider.generate(text))
        # Then
        self.assertEqual(proposals, [])

    def test_minimum_tense_count_is_opt_in(self) -> None:
        # Given
        provider = TensifyInverseProvider(min_tense_syllables=2)
        # When
        below_threshold = list(provider.generate("진짜 좋아"))
        at_threshold = list(provider.generate("진짜 짱이야"))
        # Then
        self.assertEqual(below_threshold, [])
        self.assertTrue(at_threshold)

    def test_zero_hangul_syllables_avoids_division_by_zero(self) -> None:
        # Given
        provider = TensifyInverseProvider()
        # When
        non_korean_result = list(provider.generate("hello!!"))
        empty_result = list(provider.generate(""))
        # Then
        self.assertEqual(non_korean_result, [])
        self.assertEqual(empty_result, [])

    def test_minimum_tense_ratio_uses_completed_hangul_syllables(self) -> None:
        # Given
        provider = TensifyInverseProvider(min_tense_ratio=0.25)
        # When
        accepted = list(provider.generate("까나다라"))
        rejected = list(provider.generate("까나다라마"))
        # Then
        self.assertTrue(accepted)
        self.assertEqual(rejected, [])
        self.assertIn(("tense_ratio", "0.250000"), accepted[0].metadata)

    def test_rejects_invalid_candidate_limit(self) -> None:
        # Given / When / Then: max_candidates가 1 미만
        with self.assertRaisesRegex(ValueError, "1 이상"):
            TensifyInverseProvider(max_candidates=0)
        # Given / When / Then: min_tense_syllables가 1 미만
        with self.assertRaisesRegex(ValueError, "min_tense_syllables"):
            TensifyInverseProvider(min_tense_syllables=0)
        # Given / When / Then: min_tense_ratio가 [0,1] 범위 밖
        with self.assertRaisesRegex(ValueError, "min_tense_ratio"):
            TensifyInverseProvider(min_tense_ratio=1.1)
        # Given / When / Then: diversify threshold가 2 미만
        with self.assertRaisesRegex(ValueError, "diversify_from"):
            TensifyInverseProvider(diversify_from=1)

    def test_rejects_non_string_direct_call(self) -> None:
        # Given
        provider = TensifyInverseProvider()
        invalid_input = None
        # When / Then
        with self.assertRaisesRegex(TypeError, "str"):
            list(provider.generate(invalid_input))  # type: ignore[arg-type]

    def test_gateway_keeps_original_and_adds_opt_in_candidate(self) -> None:
        # Given
        gateway = Gateway(providers=[TensifyInverseProvider()])
        # When
        result = gateway.process("씨스템 점검")
        # Then
        self.assertEqual([view.text for view in result.views], ["씨스템 점검", "시스템 점검"])
        self.assertEqual(result.views[1].provider, "tensify_inverse")
        self.assertTrue(result.views[1].lossy)
        self.assertIn(("source_positions", "0"), result.views[1].metadata)

    def test_default_gateway_does_not_apply_lossy_inverse(self) -> None:
        # Given
        gateway = Gateway()
        # When
        result = gateway.process("씨스템 점검")
        # Then
        self.assertEqual([view.text for view in result.views], ["씨스템 점검"])
        self.assertFalse(result.has_lossy_views)

    def test_gateway_total_view_budget_remains_authoritative(self) -> None:
        # Given
        gateway = Gateway(
            providers=[TensifyInverseProvider(max_candidates=9)],
            max_views=3,
        )
        # When
        result = gateway.process("까따싸")
        # Then
        self.assertEqual([view.text for view in result.views], ["까따싸", "가다사", "가다싸"])
        self.assertTrue(result.truncated)


if __name__ == "__main__":
    unittest.main()
