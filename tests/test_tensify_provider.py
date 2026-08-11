import unittest

from k_safeguard import Gateway
from k_safeguard.providers import (
    TENSIFY_CANDIDATE_VERSION,
    TensifyInverseProvider,
)


class TensifyInverseProviderTest(unittest.TestCase):
    def test_reverses_all_supported_tense_initials(self) -> None:
        proposals = list(TensifyInverseProvider(max_candidates=1).generate("까따빠싸짜"))

        self.assertEqual([item.text for item in proposals], ["가다바사자"])
        self.assertTrue(proposals[0].lossy)
        self.assertIsNone(proposals[0].confidence)

    def test_preserves_vowels_and_final_consonants(self) -> None:
        proposal = next(TensifyInverseProvider().generate("꼭 썼다"))

        self.assertEqual(proposal.text, "곡 섰다")

    def test_orders_more_replacements_before_partial_candidates(self) -> None:
        proposals = list(TensifyInverseProvider(max_candidates=3).generate("까싸"))

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
                ("source_positions", "0,1"),
                ("generator_version", TENSIFY_CANDIDATE_VERSION),
            ),
        )

    def test_caps_candidates_deterministically(self) -> None:
        provider = TensifyInverseProvider(max_candidates=2)

        first = [item.text for item in provider.generate("까따싸")]
        second = [item.text for item in provider.generate("까따싸")]

        self.assertEqual(first, second)
        self.assertEqual(first, ["가다사", "가다싸"])

    def test_returns_no_candidate_without_tense_syllable(self) -> None:
        self.assertEqual(list(TensifyInverseProvider().generate("시스템 점검")), [])

    def test_minimum_tense_count_is_opt_in(self) -> None:
        provider = TensifyInverseProvider(min_tense_syllables=2)

        self.assertEqual(list(provider.generate("진짜 좋아")), [])
        self.assertTrue(list(provider.generate("진짜 짱이야")))

    def test_minimum_tense_ratio_uses_completed_hangul_syllables(self) -> None:
        provider = TensifyInverseProvider(min_tense_ratio=0.25)

        accepted = list(provider.generate("까나다라"))
        rejected = list(provider.generate("까나다라마"))

        self.assertTrue(accepted)
        self.assertEqual(rejected, [])
        self.assertIn(("tense_ratio", "0.250000"), accepted[0].metadata)

    def test_rejects_invalid_candidate_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "1 이상"):
            TensifyInverseProvider(max_candidates=0)

        with self.assertRaisesRegex(ValueError, "min_tense_syllables"):
            TensifyInverseProvider(min_tense_syllables=0)
        with self.assertRaisesRegex(ValueError, "min_tense_ratio"):
            TensifyInverseProvider(min_tense_ratio=1.1)

    def test_rejects_non_string_direct_call(self) -> None:
        with self.assertRaisesRegex(TypeError, "str"):
            list(TensifyInverseProvider().generate(None))  # type: ignore[arg-type]

    def test_gateway_keeps_original_and_adds_opt_in_candidate(self) -> None:
        result = Gateway(providers=[TensifyInverseProvider()]).process("씨스템 점검")

        self.assertEqual([view.text for view in result.views], ["씨스템 점검", "시스템 점검"])
        self.assertEqual(result.views[1].provider, "tensify_inverse")
        self.assertTrue(result.views[1].lossy)
        self.assertIn(("source_positions", "0"), result.views[1].metadata)

    def test_default_gateway_does_not_apply_lossy_inverse(self) -> None:
        result = Gateway().process("씨스템 점검")

        self.assertEqual([view.text for view in result.views], ["씨스템 점검"])
        self.assertFalse(result.has_lossy_views)

    def test_gateway_total_view_budget_remains_authoritative(self) -> None:
        result = Gateway(
            providers=[TensifyInverseProvider(max_candidates=9)],
            max_views=3,
        ).process("까따싸")

        self.assertEqual([view.text for view in result.views], ["까따싸", "가다사", "가다싸"])
        self.assertTrue(result.truncated)


if __name__ == "__main__":
    unittest.main()
