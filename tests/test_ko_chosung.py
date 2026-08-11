import unittest

from ko_chosung import ChosungLexicon, chosung_signature, generate_chosung_candidates


class ChosungSignatureTest(unittest.TestCase):
    def test_builds_signature_for_hangul_syllables(self) -> None:
        self.assertEqual(chosung_signature("한국어"), "ㅎㄱㅇ")

    def test_rejects_non_hangul_words(self) -> None:
        self.assertIsNone(chosung_signature("AI모델"))
        self.assertIsNone(chosung_signature(""))


class ChosungLexiconTest(unittest.TestCase):
    def test_keeps_frequency_order_and_deduplicates(self) -> None:
        lexicon = ChosungLexicon(["시스템", "산사태", "시스템", "system"])
        self.assertEqual(lexicon.word_count, 2)
        self.assertEqual(
            [entry.word for entry in lexicon.match("ㅅㅅㅌ", 3)],
            ["시스템", "산사태"],
        )

    def test_matches_mixed_syllable_and_initial_pattern(self) -> None:
        lexicon = ChosungLexicon(["설정을", "설정은", "수정이"])
        self.assertEqual(
            [entry.word for entry in lexicon.match("ㅅ정ㅇ", 3)],
            ["설정을", "설정은", "수정이"],
        )


class GenerateChosungCandidatesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.lexicon = ChosungLexicon(
            ["시스템", "산사태", "설정을", "설정은", "한국어", "한글은"]
        )

    def test_preserves_original_and_returns_ranked_candidates(self) -> None:
        result = generate_chosung_candidates("ㅅㅅㅌ 점검", self.lexicon)
        self.assertEqual(result.candidates[0].text, "ㅅㅅㅌ 점검")
        self.assertEqual(result.candidates[1].text, "시스템 점검")
        self.assertTrue(result.candidates[1].lossy)
        self.assertEqual(result.candidates[1].covered_initials, 3)
        self.assertEqual(result.matched_spans, 1)

    def test_expands_partial_chosung_pattern(self) -> None:
        result = generate_chosung_candidates("ㅅ정ㅇ 확인", self.lexicon, min_initials=2)
        texts = [candidate.text for candidate in result.candidates]
        self.assertIn("설정을 확인", texts)
        self.assertIn("설정은 확인", texts)

    def test_preserves_repeated_chat_initials(self) -> None:
        lexicon = ChosungLexicon(["크크크", "하하하"])
        result = generate_chosung_candidates("ㅋㅋㅋ ㅎㅎㅎ", lexicon)
        self.assertEqual([candidate.text for candidate in result.candidates], ["ㅋㅋㅋ ㅎㅎㅎ"])
        self.assertEqual(result.matched_spans, 0)

    def test_requires_minimum_initial_evidence(self) -> None:
        result = generate_chosung_candidates("ㅎㄱㅇ", self.lexicon, min_initials=4)
        self.assertEqual(len(result.candidates), 1)

    def test_caps_candidates_deterministically(self) -> None:
        lexicon = ChosungLexicon(["시스템", "산사태", "소식통", "솜사탕"])
        first = generate_chosung_candidates("ㅅㅅㅌ", lexicon, max_candidates=3)
        second = generate_chosung_candidates("ㅅㅅㅌ", lexicon, max_candidates=3)
        self.assertEqual(first, second)
        self.assertEqual(len(first.candidates), 3)
        self.assertTrue(first.truncated)

    def test_tracks_original_offsets(self) -> None:
        result = generate_chosung_candidates("A:ㅅㅅㅌ!", self.lexicon)
        replacement = result.candidates[1].replacements[0]
        self.assertEqual((replacement.source_start, replacement.source_end), (2, 5))
        self.assertEqual((replacement.before, replacement.after), ("ㅅㅅㅌ", "시스템"))

    def test_rejects_non_string_input(self) -> None:
        with self.assertRaisesRegex(TypeError, "str"):
            generate_chosung_candidates(None, self.lexicon)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
