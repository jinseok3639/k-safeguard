import unittest

from k_safeguard.chosung import CHOSUNG_CANDIDATE_VERSION, ChosungLexicon
from k_safeguard.providers import ChosungLexiconProvider


class ChosungLexiconProviderMetadataTest(unittest.TestCase):
    def test_trusted_repeated_initial_word_reaches_gateway_candidate(self) -> None:
        lexicon = ChosungLexicon.from_sources([("domain", ["제조", "방법"])])
        provider = ChosungLexiconProvider(lexicon, min_initials=2)

        proposals = list(provider.generate("ㅈㅈ ㅂㅂ"))

        self.assertIn("제조 방법", [proposal.text for proposal in proposals])
        self.assertTrue(
            all(
                ("generator_version", CHOSUNG_CANDIDATE_VERSION)
                in proposal.metadata
                for proposal in proposals
            )
        )

    def test_direct_match_metadata_reflects_computed_values(self) -> None:
        # Given
        lexicon = ChosungLexicon.from_sources([("domain", ["시스템"])])
        provider = ChosungLexiconProvider(lexicon)
        # When
        proposals = list(provider.generate("ㅅㅅㅌ 점검"))
        # Then
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].text, "시스템 점검")
        self.assertEqual(
            proposals[0].metadata,
            (
                ("covered_initials", "3"),
                ("rank_score", "0"),
                ("lexicon_sources", "domain"),
                ("max_segment_count", "1"),
                ("partial_replacement_count", "0"),
                ("partial_ranges", ""),
                ("generator_version", CHOSUNG_CANDIDATE_VERSION),
            ),
        )

    def test_segmented_match_metadata_reflects_computed_values(self) -> None:
        # Given
        lexicon = ChosungLexicon.from_sources(
            [("domain", ["시스템", "프롬프트"])]
        )
        provider = ChosungLexiconProvider(lexicon, allow_segmentation=True)
        # When
        proposals = list(provider.generate("ㅅㅅㅌㅍㄹㅍㅌ"))
        # Then
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].text, "시스템프롬프트")
        self.assertEqual(
            proposals[0].metadata,
            (
                ("covered_initials", "7"),
                ("rank_score", "1"),
                ("lexicon_sources", "domain"),
                ("max_segment_count", "2"),
                ("partial_replacement_count", "0"),
                ("partial_ranges", ""),
                ("generator_version", CHOSUNG_CANDIDATE_VERSION),
            ),
        )

    def test_partial_match_metadata_reflects_computed_values(self) -> None:
        # Given
        lexicon = ChosungLexicon.from_sources(
            [("domain", ["시스템"]), ("general", ["산사태"])]
        )
        provider = ChosungLexiconProvider(
            lexicon,
            allow_partial_restoration=True,
            partial_sources=("domain",),
        )
        # When
        proposals = list(provider.generate("ㄱㄱㅅㅅㅌㄴ"))
        # Then
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].text, "ㄱㄱ시스템ㄴ")
        self.assertEqual(
            proposals[0].metadata,
            (
                ("covered_initials", "3"),
                ("rank_score", "0"),
                ("lexicon_sources", "domain"),
                ("max_segment_count", "1"),
                ("partial_replacement_count", "1"),
                ("partial_ranges", "2:5"),
                ("generator_version", CHOSUNG_CANDIDATE_VERSION),
            ),
        )

    def test_rejects_one_string_as_partial_sources(self) -> None:
        # Given
        lexicon = ChosungLexicon.from_sources([("domain", ["시스템"])])
        # When / Then
        with self.assertRaisesRegex(TypeError, "iterable"):
            ChosungLexiconProvider(
                lexicon,
                allow_partial_restoration=True,
                partial_sources="domain",
            )

    def test_yields_nothing_when_no_span_matches(self) -> None:
        # Given
        lexicon = ChosungLexicon.from_sources([("domain", ["시스템"])])
        provider = ChosungLexiconProvider(lexicon)
        # When
        proposals = list(provider.generate("안녕하세요"))
        # Then
        self.assertEqual(proposals, [])


if __name__ == "__main__":
    unittest.main()
