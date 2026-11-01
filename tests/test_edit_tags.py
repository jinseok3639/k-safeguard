"""글자 편집 태거 primitives 테스트. 표준 라이브러리만으로 돈다."""

import unittest

from k_safeguard.edit_tags import (
    DELETE,
    KEEP,
    SUBSTITUTE,
    CharEdit,
    apply_edits,
    is_syllable,
    jamo_features,
    join_syllable,
    split_chunks,
)
from k_safeguard.normalization import COMPAT_CHO, COMPAT_JONG, COMPAT_JUNG


class JamoFeaturesTest(unittest.TestCase):
    def test_syllable_fills_all_three_slots_offset_by_one(self) -> None:
        # Given / When / Then — 각: ㄱ(0) ㅏ(0) ㄱ(1), 0은 '없음'으로 예약돼 있다
        self.assertEqual(jamo_features("각"), (1, 1, 2))
        self.assertEqual(jamo_features("가"), (1, 1, 1))

    def test_last_syllable_is_the_largest_index(self) -> None:
        # Given / When / Then
        self.assertEqual(
            jamo_features("힣"), (len(COMPAT_CHO), len(COMPAT_JUNG), len(COMPAT_JONG))
        )

    def test_consonant_in_both_tables_counts_as_initial(self) -> None:
        # Given / When / Then — ㄱ은 초성·종성에 다 있다
        self.assertEqual(jamo_features("ㄱ"), (1, 0, 0))

    def test_vowel_fills_only_the_medial_slot(self) -> None:
        # Given / When / Then
        self.assertEqual(jamo_features("ㅏ"), (0, 1, 0))

    def test_coda_only_cluster_fills_only_the_final_slot(self) -> None:
        # Given / When / Then — ㄳ은 초성에 없다
        self.assertEqual(jamo_features("ㄳ"), (0, 0, COMPAT_JONG.index("ㄳ") + 1))

    def test_non_hangul_has_no_features(self) -> None:
        # Given / When / Then
        for char in ("a", " ", "!", "​", "😀"):
            self.assertEqual(jamo_features(char), (0, 0, 0))


class JoinSyllableTest(unittest.TestCase):
    def test_inverts_features(self) -> None:
        # Given / When / Then
        for char in ("가", "각", "뷁", "힣"):
            cho, jung, jong = jamo_features(char)
            self.assertEqual(join_syllable(cho - 1, jung - 1, jong - 1), char)

    def test_rejects_out_of_range_indices(self) -> None:
        # Given / When / Then
        with self.assertRaises(ValueError):
            join_syllable(19, 0, 0)

    def test_is_syllable_checks_the_precomposed_range(self) -> None:
        # Given / When / Then
        self.assertTrue(is_syllable("가"))
        self.assertTrue(is_syllable("힣"))
        self.assertFalse(is_syllable("ㄱ"))
        self.assertFalse(is_syllable("가나"))


class SplitChunksTest(unittest.TestCase):
    def test_short_text_stays_whole(self) -> None:
        # Given / When / Then
        self.assertEqual(split_chunks("가나. 다라.", 100), ["가나. 다라."])

    def test_empty_text_has_no_chunks(self) -> None:
        # Given / When / Then
        self.assertEqual(split_chunks("", 10), [])

    def test_prefers_sentence_boundaries(self) -> None:
        # Given / When / Then
        self.assertEqual(split_chunks("가나다. 라마바. 사아", 6), ["가나다. ", "라마바. ", "사아"])

    def test_falls_back_to_spaces(self) -> None:
        # Given / When / Then
        self.assertEqual(split_chunks("가나 다라 마바", 4), ["가나 ", "다라 ", "마바"])

    def test_hard_cuts_without_any_boundary(self) -> None:
        # Given / When / Then
        self.assertEqual(split_chunks("가나다라마", 2), ["가나", "다라", "마"])

    def test_limit_stops_early_and_keeps_the_prefix(self) -> None:
        for text in ("가나다. 라마바. 사아자. 차카", "가나 다라 마바 사아", "가" * 20, "가나다라. " * 5):
            for limit in (1, 2, 3):
                with self.subTest(text=text, limit=limit):
                    # When
                    chunks = split_chunks(text, 4, limit=limit)
                    # Then
                    self.assertEqual(chunks, split_chunks(text, 4)[:limit])

    def test_rejects_non_positive_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "limit"):
            split_chunks("가", 1, limit=0)

    def test_joining_restores_the_input_and_respects_the_limit(self) -> None:
        # Given
        texts = ("가나다. 라마!\n\n바사 아자차카타파하 ", "   ", "...!!!", "가" * 50, " 가 나 ")
        for text in texts:
            for limit in (1, 2, 3, 7):
                # When
                chunks = split_chunks(text, limit)
                # Then
                self.assertEqual("".join(chunks), text)
                self.assertTrue(all(0 < len(chunk) <= limit for chunk in chunks))

    def test_rejects_non_positive_limit(self) -> None:
        # Given / When / Then
        with self.assertRaises(ValueError):
            split_chunks("가", 0)


class ApplyEditsTest(unittest.TestCase):
    def test_keep_only_returns_input_with_no_edits(self) -> None:
        # Given / When
        restored = apply_edits("가나", [CharEdit(), CharEdit()], 0.5)
        # Then
        self.assertEqual(restored, ("가나", 0, 0.0))

    def test_applies_confident_substitution_and_deletion(self) -> None:
        # Given
        edits = [
            CharEdit(SUBSTITUTE, "법", 0.9),
            CharEdit(DELETE, confidence=0.7),
            CharEdit(KEEP),
        ]
        # When
        restored, changed, confidence = apply_edits("뻡!다", edits, 0.5)
        # Then
        self.assertEqual(restored, "법다")
        self.assertEqual(changed, 2)
        self.assertAlmostEqual(confidence, 0.8)

    def test_abstains_below_threshold(self) -> None:
        # Given
        edits = [CharEdit(SUBSTITUTE, "법", 0.49), CharEdit(DELETE, confidence=0.1)]
        # When / Then
        self.assertEqual(apply_edits("뻡!", edits, 0.5), ("뻡!", 0, 0.0))

    def test_threshold_is_inclusive(self) -> None:
        # Given
        edits = [CharEdit(SUBSTITUTE, "법", 0.5)]
        # When / Then
        self.assertEqual(apply_edits("뻡", edits, 0.5)[0], "법")

    def test_inserts_space_before_the_character(self) -> None:
        # Given
        edits = [CharEdit(), CharEdit(space_confidence=0.9)]
        # When
        restored, changed, _ = apply_edits("가나", edits, 0.5)
        # Then
        self.assertEqual(restored, "가 나")
        self.assertEqual(changed, 1)

    def test_space_needs_at_least_half_even_with_a_low_threshold(self) -> None:
        # Given — 임계값이 낮아도 모델이 '공백 없음'을 더 높게 본 자리에는 넣지 않는다
        edits = [CharEdit(), CharEdit(space_confidence=0.4)]
        # When / Then
        self.assertEqual(apply_edits("가나", edits, 0.1)[0], "가나")

    def test_space_decision_is_independent_of_the_character_edit(self) -> None:
        # Given — 글자 편집은 기권해도 공백은 넣는다
        edits = [CharEdit(), CharEdit(DELETE, confidence=0.2, space_confidence=0.9)]
        # When / Then
        self.assertEqual(apply_edits("가나", edits, 0.5)[0], "가 나")

    def test_rejects_length_mismatch(self) -> None:
        # Given / When / Then
        with self.assertRaises(ValueError):
            apply_edits("가나", [CharEdit()], 0.5)


if __name__ == "__main__":
    unittest.main()
