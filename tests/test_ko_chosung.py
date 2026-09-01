import unittest

from k_safeguard.chosung import (
    ChosungLexicon,
    chosung_signature,
    expand_korean_noun_particles,
    generate_chosung_candidates,
)


class ChosungSignatureTest(unittest.TestCase):
    def test_builds_signature_for_hangul_syllables(self) -> None:
        # Given
        word = "한국어"
        # When
        signature = chosung_signature(word)
        # Then
        self.assertEqual(signature, "ㅎㄱㅇ")

    def test_rejects_non_hangul_words(self) -> None:
        # Given
        mixed_script_word = "AI모델"
        empty_word = ""
        # When
        mixed_script_signature = chosung_signature(mixed_script_word)
        empty_signature = chosung_signature(empty_word)
        # Then
        self.assertIsNone(mixed_script_signature)
        self.assertIsNone(empty_signature)

    def test_expands_particles_by_final_consonant(self) -> None:
        # Given
        words = ["정책", "가드레일", "보안"]
        # When
        expanded = expand_korean_noun_particles(words)
        # Then
        self.assertIn("정책은", expanded)
        self.assertIn("정책으로", expanded)
        self.assertIn("가드레일은", expanded)
        self.assertIn("가드레일로", expanded)
        self.assertIn("보안을", expanded)
        self.assertNotIn("보안를", expanded)

    def test_expands_euro_ro_particle_by_batchim_type(self) -> None:
        # Given
        word_with_regular_batchim = ["정책"]
        word_with_rieul_batchim = ["가드레일"]
        word_without_batchim = ["정보"]
        # When
        regular_batchim = expand_korean_noun_particles(word_with_regular_batchim)
        rieul_batchim = expand_korean_noun_particles(word_with_rieul_batchim)
        no_batchim = expand_korean_noun_particles(word_without_batchim)
        # Then
        self.assertIn("정책으로", regular_batchim)
        self.assertIn("가드레일로", rieul_batchim)
        self.assertNotIn("가드레일으로", rieul_batchim)
        self.assertIn("정보로", no_batchim)
        self.assertNotIn("정보으로", no_batchim)

    def test_expand_particles_rejects_non_string_words(self) -> None:
        # Given
        words_with_invalid_item = ["정책", 123]
        # When / Then
        with self.assertRaisesRegex(TypeError, "str"):
            expand_korean_noun_particles(words_with_invalid_item)  # type: ignore[list-item]

    def test_expand_particles_preserves_non_hangul_words_unexpanded(self) -> None:
        # Given
        words = ["AI모델"]
        # When
        expanded = expand_korean_noun_particles(words)
        # Then
        self.assertEqual(expanded, ("AI모델",))

    def test_expand_particles_deduplicates_repeated_input_words(self) -> None:
        # Given
        duplicated_words = ["정책", "정책"]
        # When
        expanded = expand_korean_noun_particles(duplicated_words)
        # Then
        self.assertEqual(expanded.count("정책"), 1)


class ChosungLexiconTest(unittest.TestCase):
    def test_keeps_frequency_order_and_deduplicates(self) -> None:
        # Given
        words = ["시스템", "산사태", "시스템", "system"]
        # When
        lexicon = ChosungLexicon(words)
        # Then
        self.assertEqual(lexicon.word_count, 2)
        self.assertEqual(
            [entry.word for entry in lexicon.match("ㅅㅅㅌ", 3)],
            ["시스템", "산사태"],
        )

    def test_matches_mixed_syllable_and_initial_pattern(self) -> None:
        # Given
        lexicon = ChosungLexicon(["설정을", "설정은", "수정이"])
        # When
        matches = lexicon.match("ㅅ정ㅇ", 3)
        # Then
        self.assertEqual(
            [entry.word for entry in matches],
            ["설정을", "설정은", "수정이"],
        )

    def test_prioritizes_sources_and_assigns_duplicate_to_first_source(self) -> None:
        # Given
        sources = [
            ("user", ["시스템", "산사태"]),
            ("wordfreq:ko", ["산사태", "소식통"]),
        ]
        # When
        lexicon = ChosungLexicon.from_sources(sources)
        entries = lexicon.match("ㅅㅅㅌ", 3)
        # Then
        self.assertEqual([entry.word for entry in entries], ["시스템", "산사태", "소식통"])
        self.assertEqual(
            [entry.source for entry in entries],
            ["user", "user", "wordfreq:ko"],
        )
        self.assertEqual(lexicon.source_counts, (("user", 2), ("wordfreq:ko", 1)))

    def test_rejects_duplicate_or_empty_source_names(self) -> None:
        # Given / When / Then: 같은 이름의 source가 두 번 선언됨
        with self.assertRaisesRegex(ValueError, "중복"):
            ChosungLexicon.from_sources([("user", ["시스템"]), ("user", ["산사태"])])
        # Given / When / Then: source 이름이 빈 문자열
        with self.assertRaisesRegex(ValueError, "비어 있지 않은"):
            ChosungLexicon.from_sources([("", ["시스템"])])

    def test_segments_long_initial_pattern_with_bounded_parts(self) -> None:
        # Given
        lexicon = ChosungLexicon.from_sources(
            [("domain", ["시스템", "프롬프트", "시스템프롬프트"])]
        )
        # When
        matches = lexicon.match_segmented("ㅅㅅㅌㅍㄹㅍㅌ", 3)
        # Then
        self.assertEqual(matches[0].word, "시스템프롬프트")
        self.assertEqual(
            [entry.word for entry in matches[0].entries],
            ["시스템", "프롬프트"],
        )

    def test_segment_match_requires_complete_initial_pattern(self) -> None:
        # Given
        lexicon = ChosungLexicon(["시스템", "프롬프트"])
        # When / Then: 초성이 아닌 완성형 음절이 섞인 pattern은 분할 불가
        self.assertEqual(lexicon.match_segmented("시스템ㅍㄹㅍㅌ", 3), ())
        # Given / When / Then: max_segments가 허용 범위(2~4) 밖
        with self.assertRaisesRegex(ValueError, "2~4"):
            lexicon.match_segmented("ㅅㅅㅌㅍㄹㅍㅌ", 3, max_segments=5)
        # Given / When / Then: max_options_per_segment가 허용 범위(1~4) 밖
        with self.assertRaisesRegex(ValueError, "1~4"):
            lexicon.match_segmented(
                "ㅅㅅㅌㅍㄹㅍㅌ",
                3,
                max_options_per_segment=5,
            )

    def test_matches_only_bounded_partial_words_from_trusted_sources(self) -> None:
        # Given
        lexicon = ChosungLexicon.from_sources(
            [
                ("domain", ["시스템"]),
                ("general", ["시스템프롬프트"]),
            ]
        )
        # When
        matches = lexicon.match_partial(
            "ㄱㄱㅅㅅㅌㄴ",
            3,
            sources=("domain",),
        )
        no_match = lexicon.match_partial("ㅅㅅㅌ", 3, sources=("domain",))
        # Then
        self.assertEqual(len(matches), 1)
        self.assertEqual((matches[0].start, matches[0].end), (2, 5))
        self.assertEqual(matches[0].entry.word, "시스템")
        self.assertEqual(no_match, ())

    def test_rejects_non_string_word(self) -> None:
        # Given
        words_with_invalid_item = [123]
        # When / Then
        with self.assertRaisesRegex(TypeError, "str"):
            ChosungLexicon(words_with_invalid_item)  # type: ignore[list-item]

    def test_segmented_backtracks_past_segment_count_cap(self) -> None:
        # Given
        lexicon = ChosungLexicon.from_sources(
            [("domain", ["가", "나", "다", "라"])], min_word_length=1
        )
        # When
        matches = lexicon.match_segmented("ㄱㄴㄷㄹ", 5, max_segments=2)
        # Then
        self.assertEqual(matches, ())

    def test_segmented_keeps_lower_rank_duplicate_word(self) -> None:
        # Given
        lexicon = ChosungLexicon.from_sources(
            [("domain", ["가나", "다", "가", "나다"])], min_word_length=1
        )
        # When
        matches = lexicon.match_segmented("ㄱㄴㄷ", 5, max_segments=2)
        # Then
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].word, "가나다")
        self.assertEqual([entry.word for entry in matches[0].entries], ["가나", "다"])

    def test_match_partial_rejects_non_positive_min_initials(self) -> None:
        # Given
        lexicon = ChosungLexicon(["시스템"])
        # When / Then
        with self.assertRaisesRegex(ValueError, "min_initials"):
            lexicon.match_partial("ㅅㅅㅌ", 3, sources=("default",), min_initials=0)

    def test_match_partial_returns_empty_for_impure_or_empty_pattern(self) -> None:
        # Given
        lexicon = ChosungLexicon(["시스템"])
        # When
        empty_pattern_result = lexicon.match_partial("", 3, sources=("default",))
        impure_pattern_result = lexicon.match_partial(
            "시스템", 3, sources=("default",)
        )
        # Then
        self.assertEqual(empty_pattern_result, ())
        self.assertEqual(impure_pattern_result, ())

    def test_rejects_invalid_word_length_bounds(self) -> None:
        # Given / When / Then: min_word_length가 1 미만
        with self.assertRaisesRegex(ValueError, "단어 길이"):
            ChosungLexicon(["시스템"], min_word_length=0)
        # Given / When / Then: max_word_length가 min_word_length보다 작음
        with self.assertRaisesRegex(ValueError, "단어 길이"):
            ChosungLexicon(["시스템"], min_word_length=5, max_word_length=3)

    def test_rejects_non_positive_limit_on_match_methods(self) -> None:
        # Given
        lexicon = ChosungLexicon(["시스템"])
        # When / Then
        with self.assertRaisesRegex(ValueError, "limit"):
            lexicon.match("ㅅㅅㅌ", 0)
        with self.assertRaisesRegex(ValueError, "limit"):
            lexicon.match_segmented("ㅅㅅㅌ", 0)
        with self.assertRaisesRegex(ValueError, "limit"):
            lexicon.match_partial("ㅅㅅㅌ", 0, sources=("default",))

    def test_match_partial_rejects_invalid_sources(self) -> None:
        # Given
        lexicon = ChosungLexicon(["시스템"])
        # When / Then: 문자열 하나를 그대로 넘기면 iterable로 취급하지 않는다
        with self.assertRaisesRegex(TypeError, "iterable"):
            lexicon.match_partial("ㅅㅅㅌ", 3, sources="default")
        # When / Then: source 목록이 비어 있음
        with self.assertRaisesRegex(ValueError, "source"):
            lexicon.match_partial("ㅅㅅㅌ", 3, sources=())
        # When / Then: source 이름이 빈 문자열
        with self.assertRaisesRegex(ValueError, "source"):
            lexicon.match_partial("ㅅㅅㅌ", 3, sources=("",))


class GenerateChosungCandidatesTest(unittest.TestCase):
    def setUp(self) -> None:
        # 모든 테스트가 공유하는 기본 렉시콘(Given의 일부)
        self.lexicon = ChosungLexicon(
            ["시스템", "산사태", "설정을", "설정은", "한국어", "한글은"]
        )

    def test_preserves_original_and_returns_ranked_candidates(self) -> None:
        # Given
        text = "ㅅㅅㅌ 점검"
        # When
        result = generate_chosung_candidates(text, self.lexicon)
        # Then
        self.assertEqual(result.candidates[0].text, "ㅅㅅㅌ 점검")
        self.assertEqual(result.candidates[1].text, "시스템 점검")
        self.assertTrue(result.candidates[1].lossy)
        self.assertEqual(result.candidates[1].covered_initials, 3)
        self.assertEqual(result.matched_spans, 1)

    def test_expands_partial_chosung_pattern(self) -> None:
        # Given
        text = "ㅅ정ㅇ 확인"
        # When
        result = generate_chosung_candidates(text, self.lexicon, min_initials=2)
        texts = [candidate.text for candidate in result.candidates]
        # Then
        self.assertIn("설정을 확인", texts)
        self.assertIn("설정은 확인", texts)

    def test_preserves_unmatched_repeated_chat_initials(self) -> None:
        # Given
        lexicon = ChosungLexicon(["시스템"])
        text = "ㅋㅋㅋ ㅎㅎㅎ"
        # When
        result = generate_chosung_candidates(text, lexicon)
        # Then
        self.assertEqual([candidate.text for candidate in result.candidates], ["ㅋㅋㅋ ㅎㅎㅎ"])
        self.assertEqual(result.matched_spans, 0)

    def test_restores_repeated_initials_with_trusted_direct_match(self) -> None:
        # Given
        lexicon = ChosungLexicon(["제조", "진주", "방법"])
        text = "ㅈㅈ ㅂㅂ"
        # When
        result = generate_chosung_candidates(text, lexicon, min_initials=2)
        candidate_texts = [candidate.text for candidate in result.candidates]
        # Then
        self.assertIn("제조 방법", candidate_texts)
        self.assertIn("진주 방법", candidate_texts)
        self.assertEqual(result.matched_spans, 2)

    def test_does_not_segment_unmatched_repeated_chat_initials(self) -> None:
        # Given
        lexicon = ChosungLexicon(["카", "크"], min_word_length=1)
        text = "ㅋㅋ"
        # When
        result = generate_chosung_candidates(
            text,
            lexicon,
            min_initials=2,
            allow_segmentation=True,
        )
        # Then
        self.assertEqual([candidate.text for candidate in result.candidates], [text])
        self.assertEqual(result.matched_spans, 0)

    def test_does_not_partially_restore_repeated_chat_initials(self) -> None:
        # Given
        lexicon = ChosungLexicon.from_sources([("domain", ["카카"])])
        text = "ㅋㅋㅋ"
        # When
        result = generate_chosung_candidates(
            text,
            lexicon,
            allow_partial_restoration=True,
            partial_sources=("domain",),
            min_partial_initials=2,
        )
        # Then
        self.assertEqual([candidate.text for candidate in result.candidates], [text])
        self.assertEqual(result.matched_spans, 0)

    def test_requires_minimum_initial_evidence(self) -> None:
        # Given
        text = "ㅎㄱㅇ"
        # When
        result = generate_chosung_candidates(text, self.lexicon, min_initials=4)
        # Then
        self.assertEqual(len(result.candidates), 1)

    def test_caps_candidates_deterministically(self) -> None:
        # Given
        lexicon = ChosungLexicon(["시스템", "산사태", "소식통", "솜사탕"])
        text = "ㅅㅅㅌ"
        # When
        first = generate_chosung_candidates(text, lexicon, max_candidates=3)
        second = generate_chosung_candidates(text, lexicon, max_candidates=3)
        # Then
        self.assertEqual(first, second)
        self.assertEqual(len(first.candidates), 3)
        self.assertTrue(first.truncated)

    def test_tracks_original_offsets(self) -> None:
        # Given
        text = "A:ㅅㅅㅌ!"
        # When
        result = generate_chosung_candidates(text, self.lexicon)
        replacement = result.candidates[1].replacements[0]
        # Then
        self.assertEqual((replacement.source_start, replacement.source_end), (2, 5))
        self.assertEqual((replacement.before, replacement.after), ("ㅅㅅㅌ", "시스템"))

    def test_tracks_priority_lexicon_source(self) -> None:
        # Given
        lexicon = ChosungLexicon.from_sources(
            [("domain", ["보안정책"]), ("general", ["병원정책"])]
        )
        text = "ㅂㅇㅈㅊ"
        # When
        result = generate_chosung_candidates(text, lexicon)
        replacement = result.candidates[1].replacements[0]
        # Then
        self.assertEqual(replacement.after, "보안정책")
        self.assertEqual(replacement.lexicon_source, "domain")
        self.assertEqual(replacement.source_rank, 0)

    def test_segmentation_is_opt_in_and_traces_component_words(self) -> None:
        # Given
        lexicon = ChosungLexicon.from_sources(
            [("domain", ["시스템", "프롬프트"])]
        )
        text = "ㅅㅅㅌㅍㄹㅍㅌ"
        # When
        disabled = generate_chosung_candidates(text, lexicon)
        enabled = generate_chosung_candidates(
            text,
            lexicon,
            allow_segmentation=True,
        )
        # Then
        self.assertEqual(len(disabled.candidates), 1)
        self.assertEqual(enabled.candidates[1].text, "시스템프롬프트")
        replacement = enabled.candidates[1].replacements[0]
        self.assertEqual(replacement.segment_words, ("시스템", "프롬프트"))
        self.assertEqual(replacement.segment_sources, ("domain", "domain"))

    def test_segmentation_uses_only_slots_left_after_direct_candidates(self) -> None:
        # Given
        lexicon = ChosungLexicon(
            ["가가", "나다", "고기너도", "구구누두", "기게노디"]
        )
        text = "ㄱㄱㄴㄷ"
        # When
        direct = generate_chosung_candidates(
            text,
            lexicon,
            max_options_per_span=3,
            max_candidates=4,
        )
        segmented = generate_chosung_candidates(
            text,
            lexicon,
            max_options_per_span=3,
            max_candidates=4,
            allow_segmentation=True,
        )
        direct_texts = {candidate.text for candidate in direct.candidates}
        segmented_texts = {candidate.text for candidate in segmented.candidates}
        # Then
        self.assertEqual(len(direct_texts), 4)
        self.assertLessEqual(direct_texts, segmented_texts)
        self.assertNotIn("가가나다", segmented_texts)
        self.assertTrue(segmented.truncated)

    def test_partial_policy_preserves_segmented_candidate_set_at_cap(self) -> None:
        # Given
        lexicon = ChosungLexicon.from_sources(
            [
                ("domain", ["가가", "나다"]),
                ("general", ["고기너도", "구구누두"]),
            ]
        )
        text = "ㄱㄱㄴㄷ"
        # When
        segmented = generate_chosung_candidates(
            text,
            lexicon,
            max_options_per_span=3,
            max_candidates=4,
            allow_segmentation=True,
        )
        partial = generate_chosung_candidates(
            text,
            lexicon,
            max_options_per_span=3,
            max_candidates=4,
            allow_segmentation=True,
            allow_partial_restoration=True,
            partial_sources=("domain",),
            min_partial_initials=2,
        )
        segmented_texts = {candidate.text for candidate in segmented.candidates}
        partial_texts = {candidate.text for candidate in partial.candidates}
        # Then
        self.assertLessEqual(segmented_texts, partial_texts)
        self.assertTrue(partial.truncated)

    def test_partial_restoration_preserves_unmatched_initials_and_traces_range(self) -> None:
        # Given
        lexicon = ChosungLexicon.from_sources(
            [("domain", ["시스템"]), ("general", ["산사태"])]
        )
        text = "ㄱㄱㅅㅅㅌㄴ"
        # When
        disabled = generate_chosung_candidates(text, lexicon)
        enabled = generate_chosung_candidates(
            text,
            lexicon,
            allow_partial_restoration=True,
            partial_sources=("domain",),
        )
        # Then
        self.assertEqual(len(disabled.candidates), 1)
        self.assertEqual(enabled.candidates[1].text, "ㄱㄱ시스템ㄴ")
        self.assertEqual(enabled.candidates[1].covered_initials, 3)
        replacement = enabled.candidates[1].replacements[0]
        self.assertTrue(replacement.partial)
        self.assertEqual((replacement.source_start, replacement.source_end), (2, 5))
        self.assertEqual((replacement.before, replacement.after), ("ㅅㅅㅌ", "시스템"))
        self.assertEqual(replacement.lexicon_source, "domain")

    def test_partial_restoration_requires_explicit_trusted_source(self) -> None:
        # Given / When / Then: partial_sources를 아예 지정하지 않음
        with self.assertRaisesRegex(ValueError, "source"):
            generate_chosung_candidates(
                "ㄱㄱㅅㅅㅌㄴ",
                self.lexicon,
                allow_partial_restoration=True,
            )
        # Given / When / Then: partial_sources에 문자열 하나만 넘김(iterable 아님)
        with self.assertRaisesRegex(TypeError, "iterable"):
            generate_chosung_candidates(
                "ㄱㄱㅅㅅㅌㄴ",
                self.lexicon,
                allow_partial_restoration=True,
                partial_sources="domain",
            )

    def test_rejects_non_string_input(self) -> None:
        # Given
        invalid_input = None
        # When / Then
        with self.assertRaisesRegex(TypeError, "str"):
            generate_chosung_candidates(invalid_input, self.lexicon)  # type: ignore[arg-type]

    def test_rejects_invalid_top_level_limits(self) -> None:
        # Given
        text = "ㅅㅅㅌ"
        # When / Then: min_initials가 1 미만
        with self.assertRaisesRegex(ValueError, "min_initials"):
            generate_chosung_candidates(text, self.lexicon, min_initials=0)
        # When / Then: max_options_per_span이 1 미만
        with self.assertRaisesRegex(ValueError, "후보 제한"):
            generate_chosung_candidates(text, self.lexicon, max_options_per_span=0)
        # When / Then: max_candidates가 1 미만
        with self.assertRaisesRegex(ValueError, "후보 제한"):
            generate_chosung_candidates(text, self.lexicon, max_candidates=0)
        # When / Then: max_segments가 허용 범위(2~4) 밖(작음)
        with self.assertRaisesRegex(ValueError, "2~4"):
            generate_chosung_candidates(text, self.lexicon, max_segments=1)
        # When / Then: max_segments가 허용 범위(2~4) 밖(큼)
        with self.assertRaisesRegex(ValueError, "2~4"):
            generate_chosung_candidates(text, self.lexicon, max_segments=5)
        # When / Then: max_options_per_segment가 허용 범위(1~4) 밖(작음)
        with self.assertRaisesRegex(ValueError, "1~4"):
            generate_chosung_candidates(
                text, self.lexicon, max_options_per_segment=0
            )
        # When / Then: max_options_per_segment가 허용 범위(1~4) 밖(큼)
        with self.assertRaisesRegex(ValueError, "1~4"):
            generate_chosung_candidates(
                text, self.lexicon, max_options_per_segment=5
            )
        # When / Then: min_partial_initials가 1 미만
        with self.assertRaisesRegex(ValueError, "min_partial_initials"):
            generate_chosung_candidates(
                text, self.lexicon, min_partial_initials=0
            )
        # When / Then: max_partial_replacements가 1 미만
        with self.assertRaisesRegex(ValueError, "max_partial_replacements"):
            generate_chosung_candidates(
                text, self.lexicon, max_partial_replacements=0
            )

    def test_prefers_direct_match_over_duplicate_segmented_span(self) -> None:
        # Given
        lexicon = ChosungLexicon(["가나", "가", "나"], min_word_length=1)
        text = "ㄱㄴ"
        # When
        result = generate_chosung_candidates(
            text, lexicon, min_initials=2, allow_segmentation=True
        )
        # Then
        self.assertEqual([candidate.text for candidate in result.candidates], ["ㄱㄴ", "가나"])
        self.assertEqual(
            result.candidates[1].replacements[0].segment_words, ("가나",)
        )

    def test_max_partial_replacements_caps_combinable_partial_matches(self) -> None:
        # Given
        lexicon = ChosungLexicon.from_sources(
            [("domain", ["시스템", "보안정책"])]
        )
        text = "ㄱㄱㅅㅅㅌㄴ ㄱㄱㅂㅇㅈㅊㄴ"
        combined_text = "ㄱㄱ시스템ㄴ ㄱㄱ보안정책ㄴ"
        # When
        capped = generate_chosung_candidates(
            text,
            lexicon,
            allow_partial_restoration=True,
            partial_sources=("domain",),
            min_partial_initials=3,
        )
        uncapped = generate_chosung_candidates(
            text,
            lexicon,
            allow_partial_restoration=True,
            partial_sources=("domain",),
            min_partial_initials=3,
            max_partial_replacements=2,
        )
        # Then
        self.assertNotIn(
            combined_text, [candidate.text for candidate in capped.candidates]
        )
        self.assertIn(
            combined_text, [candidate.text for candidate in uncapped.candidates]
        )


if __name__ == "__main__":
    unittest.main()
