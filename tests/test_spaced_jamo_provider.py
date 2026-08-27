import unittest

from k_safeguard import Gateway
from k_safeguard.providers.spaced_jamo import (
    SPACED_JAMO_CANDIDATE_VERSION,
    SpacedJamoProvider,
)


class SpacedJamoProviderTest(unittest.TestCase):
    def test_restores_spaced_compound_final_across_syllable_boundary(self) -> None:
        provider = SpacedJamoProvider()

        proposals = list(provider.generate("ㅇ ㅓ ㅂ ㅅ ㅇ ㅣ"))

        self.assertEqual([proposal.text for proposal in proposals], ["없이"])
        self.assertTrue(proposals[0].lossy)
        self.assertIsNone(proposals[0].confidence)
        self.assertIn(
            ("generator_version", SPACED_JAMO_CANDIDATE_VERSION),
            proposals[0].metadata,
        )

    def test_restores_only_composable_ranges_inside_mixed_text(self) -> None:
        provider = SpacedJamoProvider()

        proposal = next(provider.generate("prefix ㅎ ㅏ ㄴ ㄱ ㅡ ㄹ suffix"))

        self.assertEqual(proposal.text, "prefix 한글 suffix")
        self.assertIn(("restored_spans", "1"), proposal.metadata)
        self.assertIn(("restored_jamo", "6"), proposal.metadata)

    def test_restores_multiple_bounded_ranges_in_one_candidate(self) -> None:
        provider = SpacedJamoProvider()

        proposal = next(provider.generate("ㅎ ㅏ ㄴ ㄱ ㅡ ㄹ / ㅌ ㅔ ㅅ ㅡ ㅌ ㅡ"))

        self.assertEqual(proposal.text, "한글 / 테스트")
        self.assertIn(("restored_spans", "2"), proposal.metadata)

    def test_does_not_change_uncomposable_chat_initials(self) -> None:
        provider = SpacedJamoProvider()

        self.assertEqual(list(provider.generate("ㅇ ㅋ ㅋ ㅋ")), [])
        self.assertEqual(list(provider.generate("ㅇㅋ ㅋㅋ")), [])

    def test_default_threshold_ignores_short_educational_example(self) -> None:
        provider = SpacedJamoProvider()

        self.assertEqual(list(provider.generate("자음 ㄱ ㅏ 설명")), [])
        proposal = next(SpacedJamoProvider(min_jamo=2).generate("자음 ㄱ ㅏ 설명"))
        self.assertEqual(proposal.text, "자음 가 설명")

    def test_does_not_remove_tabs_or_unrelated_spaces(self) -> None:
        provider = SpacedJamoProvider()

        self.assertEqual(list(provider.generate("ㅎ\tㅏ\tㄴ\tㄱ\tㅡ\tㄹ")), [])
        proposal = next(provider.generate("앞  ㅎ ㅏ ㄴ ㄱ ㅡ ㄹ  뒤"))
        self.assertEqual(proposal.text, "앞  한글  뒤")

    def test_enforces_span_and_span_count_budgets(self) -> None:
        too_long = SpacedJamoProvider(max_jamo_per_span=5)
        one_span = SpacedJamoProvider(max_spans=1)

        self.assertEqual(list(too_long.generate("ㅎ ㅏ ㄴ ㄱ ㅡ ㄹ")), [])
        proposal = next(one_span.generate("ㅎ ㅏ ㄴ ㄱ ㅡ ㄹ / ㅌ ㅔ ㅅ ㅡ ㅌ ㅡ"))
        self.assertEqual(proposal.text, "한글 / ㅌ ㅔ ㅅ ㅡ ㅌ ㅡ")

    def test_rejects_invalid_configuration_and_non_string_input(self) -> None:
        with self.assertRaisesRegex(ValueError, "min_jamo"):
            SpacedJamoProvider(min_jamo=1)
        with self.assertRaisesRegex(ValueError, "max_jamo_per_span"):
            SpacedJamoProvider(min_jamo=5, max_jamo_per_span=4)
        with self.assertRaisesRegex(ValueError, "max_spans"):
            SpacedJamoProvider(max_spans=0)

        provider = SpacedJamoProvider()
        with self.assertRaisesRegex(TypeError, "str"):
            list(provider.generate(None))  # type: ignore[arg-type]

    def test_gateway_keeps_original_and_marks_candidate_lossy(self) -> None:
        result = Gateway(providers=[SpacedJamoProvider()]).process(
            "ㅇ ㅓ ㅂ ㅅ ㅇ ㅣ"
        )

        self.assertEqual([view.text for view in result.views], ["ㅇ ㅓ ㅂ ㅅ ㅇ ㅣ", "없이"])
        self.assertEqual(result.views[1].provider, "spaced_jamo")
        self.assertTrue(result.has_lossy_views)

    def test_default_gateway_never_collapses_spaced_jamo(self) -> None:
        result = Gateway().process("ㅇ ㅓ ㅂ ㅅ ㅇ ㅣ")

        self.assertEqual([view.text for view in result.views], ["ㅇ ㅓ ㅂ ㅅ ㅇ ㅣ"])
        self.assertFalse(result.has_lossy_views)


if __name__ == "__main__":
    unittest.main()
