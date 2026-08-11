import unittest

from k_safeguard.chosung import (
    ChosungLexicon,
    chosung_signature,
    expand_korean_noun_particles,
    generate_chosung_candidates,
)


class ChosungSignatureTest(unittest.TestCase):
    def test_builds_signature_for_hangul_syllables(self) -> None:
        self.assertEqual(chosung_signature("한국어"), "ㅎㄱㅇ")

    def test_rejects_non_hangul_words(self) -> None:
        self.assertIsNone(chosung_signature("AI모델"))
        self.assertIsNone(chosung_signature(""))

    def test_expands_particles_by_final_consonant(self) -> None:
        expanded = expand_korean_noun_particles(["정책", "가드레일", "보안"])

        self.assertIn("정책은", expanded)
        self.assertIn("정책으로", expanded)
        self.assertIn("가드레일은", expanded)
        self.assertIn("가드레일로", expanded)
        self.assertIn("보안을", expanded)
        self.assertNotIn("보안를", expanded)


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

    def test_prioritizes_sources_and_assigns_duplicate_to_first_source(self) -> None:
        lexicon = ChosungLexicon.from_sources(
            [
                ("user", ["시스템", "산사태"]),
                ("wordfreq:ko", ["산사태", "소식통"]),
            ]
        )

        entries = lexicon.match("ㅅㅅㅌ", 3)
        self.assertEqual([entry.word for entry in entries], ["시스템", "산사태", "소식통"])
        self.assertEqual(
            [entry.source for entry in entries],
            ["user", "user", "wordfreq:ko"],
        )
        self.assertEqual(lexicon.source_counts, (("user", 2), ("wordfreq:ko", 1)))

    def test_rejects_duplicate_or_empty_source_names(self) -> None:
        with self.assertRaisesRegex(ValueError, "중복"):
            ChosungLexicon.from_sources([("user", ["시스템"]), ("user", ["산사태"])])
        with self.assertRaisesRegex(ValueError, "비어 있지 않은"):
            ChosungLexicon.from_sources([("", ["시스템"])])

    def test_segments_long_initial_pattern_with_bounded_parts(self) -> None:
        lexicon = ChosungLexicon.from_sources(
            [("domain", ["시스템", "프롬프트", "시스템프롬프트"])]
        )

        matches = lexicon.match_segmented("ㅅㅅㅌㅍㄹㅍㅌ", 3)
        self.assertEqual(matches[0].word, "시스템프롬프트")
        self.assertEqual(
            [entry.word for entry in matches[0].entries],
            ["시스템", "프롬프트"],
        )

    def test_segment_match_requires_complete_initial_pattern(self) -> None:
        lexicon = ChosungLexicon(["시스템", "프롬프트"])
        self.assertEqual(lexicon.match_segmented("시스템ㅍㄹㅍㅌ", 3), ())
        with self.assertRaisesRegex(ValueError, "2~4"):
            lexicon.match_segmented("ㅅㅅㅌㅍㄹㅍㅌ", 3, max_segments=5)
        with self.assertRaisesRegex(ValueError, "1~4"):
            lexicon.match_segmented(
                "ㅅㅅㅌㅍㄹㅍㅌ",
                3,
                max_options_per_segment=5,
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

    def test_tracks_priority_lexicon_source(self) -> None:
        lexicon = ChosungLexicon.from_sources(
            [("domain", ["보안정책"]), ("general", ["병원정책"])]
        )

        result = generate_chosung_candidates("ㅂㅇㅈㅊ", lexicon)
        replacement = result.candidates[1].replacements[0]
        self.assertEqual(replacement.after, "보안정책")
        self.assertEqual(replacement.lexicon_source, "domain")
        self.assertEqual(replacement.source_rank, 0)

    def test_segmentation_is_opt_in_and_traces_component_words(self) -> None:
        lexicon = ChosungLexicon.from_sources(
            [("domain", ["시스템", "프롬프트"])]
        )
        disabled = generate_chosung_candidates("ㅅㅅㅌㅍㄹㅍㅌ", lexicon)
        enabled = generate_chosung_candidates(
            "ㅅㅅㅌㅍㄹㅍㅌ",
            lexicon,
            allow_segmentation=True,
        )

        self.assertEqual(len(disabled.candidates), 1)
        self.assertEqual(enabled.candidates[1].text, "시스템프롬프트")
        replacement = enabled.candidates[1].replacements[0]
        self.assertEqual(replacement.segment_words, ("시스템", "프롬프트"))
        self.assertEqual(replacement.segment_sources, ("domain", "domain"))

    def test_rejects_non_string_input(self) -> None:
        with self.assertRaisesRegex(TypeError, "str"):
            generate_chosung_candidates(None, self.lexicon)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
