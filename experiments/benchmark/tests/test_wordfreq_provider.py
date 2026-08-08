import unittest

from k_safeguard.providers.wordfreq import WordfreqChosungProvider


class WordfreqChosungProviderTest(unittest.TestCase):
    def test_prioritizes_user_words_and_optionally_expands_particles(self) -> None:
        provider = WordfreqChosungProvider(
            word_limit=10,
            priority_words=["보안정책"],
            expand_priority_particles=True,
        )

        proposals = list(provider.generate("ㅂㅇㅈㅊㅇ 확인"))
        self.assertEqual(proposals[0].text, "보안정책은 확인")
        self.assertIn(("lexicon_sources", "user"), proposals[0].metadata)
        self.assertEqual(provider.requested_priority_word_count, 1)
        self.assertEqual(provider.priority_word_count, 11)

    def test_partial_restoration_uses_priority_source_only(self) -> None:
        provider = WordfreqChosungProvider(
            word_limit=10,
            priority_words=["시스템"],
            allow_partial_restoration=True,
        )

        proposals = list(provider.generate("ㄱㄱㅅㅅㅌㄴ"))

        partial = next(item for item in proposals if item.text == "ㄱㄱ시스템ㄴ")
        self.assertIn(("lexicon_sources", "user"), partial.metadata)
        self.assertIn(("partial_replacement_count", "1"), partial.metadata)

    def test_partial_restoration_requires_priority_words(self) -> None:
        with self.assertRaisesRegex(ValueError, "priority_words"):
            WordfreqChosungProvider(
                word_limit=10,
                allow_partial_restoration=True,
            )


if __name__ == "__main__":
    unittest.main()
