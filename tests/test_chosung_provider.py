import unittest

from k_safeguard.chosung import CHOSUNG_CANDIDATE_VERSION, ChosungLexicon
from k_safeguard.providers import ChosungLexiconProvider


class ChosungLexiconProviderMetadataTest(unittest.TestCase):
    def test_direct_match_metadata_reflects_computed_values(self) -> None:
        lexicon = ChosungLexicon.from_sources([("domain", ["시스템"])])
        provider = ChosungLexiconProvider(lexicon)

        proposals = list(provider.generate("ㅅㅅㅌ 점검"))

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
        lexicon = ChosungLexicon.from_sources(
            [("domain", ["시스템", "프롬프트"])]
        )
        provider = ChosungLexiconProvider(lexicon, allow_segmentation=True)

        proposals = list(provider.generate("ㅅㅅㅌㅍㄹㅍㅌ"))

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
        lexicon = ChosungLexicon.from_sources(
            [("domain", ["시스템"]), ("general", ["산사태"])]
        )
        provider = ChosungLexiconProvider(
            lexicon,
            allow_partial_restoration=True,
            partial_sources=("domain",),
        )

        proposals = list(provider.generate("ㄱㄱㅅㅅㅌㄴ"))

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
        lexicon = ChosungLexicon.from_sources([("domain", ["시스템"])])
        with self.assertRaisesRegex(TypeError, "iterable"):
            ChosungLexiconProvider(
                lexicon,
                allow_partial_restoration=True,
                partial_sources="domain",
            )

    def test_yields_nothing_when_no_span_matches(self) -> None:
        lexicon = ChosungLexicon.from_sources([("domain", ["시스템"])])
        provider = ChosungLexiconProvider(lexicon)

        self.assertEqual(list(provider.generate("안녕하세요")), [])


if __name__ == "__main__":
    unittest.main()
