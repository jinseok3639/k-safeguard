import unicodedata
import unittest

from hf_repo.ko_obfuscator import BASE, CHO, JONG, JUNG
from k_safeguard.normalization import (
    COMPAT_CHO,
    COMPAT_JONG,
    COMPAT_JUNG,
    HANGUL_BASE,
    NORMALIZER_VERSION,
    normalize_korean,
)


class NormalizeKoreanTest(unittest.TestCase):
    def test_jamo_tables_match_benchmark_generator(self) -> None:
        # Given
        # COMPAT_CHO/COMPAT_JUNG/COMPAT_JONG/HANGUL_BASE(k_safeguard)와
        # CHO/JUNG/JONG/BASE(hf_repo)는 import 시점에 이미 정의돼 있다.
        # When / Then
        # 별도 동작 없이 두 모듈의 상수 정의가 일치하는지 바로 검증한다.
        self.assertEqual(COMPAT_CHO, tuple(CHO))
        self.assertEqual(COMPAT_JUNG, tuple(JUNG))
        self.assertEqual(COMPAT_JONG, tuple(JONG))
        self.assertEqual(HANGUL_BASE, BASE)

    def test_clean_hangul_is_unchanged(self) -> None:
        # Given
        text = "안녕하세요. Guardrail 테스트입니다."
        # When
        result = normalize_korean(text)
        # Then
        self.assertEqual(result.text, result.original)
        self.assertFalse(result.changed)
        self.assertEqual(result.edits, ())
        self.assertEqual(result.confidence, 1.0)
        self.assertEqual(result.version, NORMALIZER_VERSION)

    def test_removes_zwsp_adjacent_to_hangul(self) -> None:
        # Given
        text = "안\u200b녕\u200b하세요"
        # When
        result = normalize_korean(text)
        # Then
        self.assertEqual(result.text, "안녕하세요")
        self.assertEqual(result.applied_rules, ("remove_hangul_zwsp",))
        self.assertFalse(result.lossy)

    def test_preserves_non_hangul_zwsp(self) -> None:
        # Given
        text = "abc\u200bdef"
        # When
        result = normalize_korean(text)
        # Then
        self.assertEqual(result.text, "abc\u200bdef")
        self.assertFalse(result.changed)

    def test_preserves_emoji_zwj_sequence(self) -> None:
        # Given
        text = "개발자 👩\u200d💻"
        # When
        result = normalize_korean(text)
        # Then
        self.assertEqual(result.text, "개발자 👩\u200d💻")

    def test_composes_modern_jamo(self) -> None:
        # Given
        # 소스 파일에 완성형으로 적으면 에디터/도구가 자모를 재조합해버릴 수
        # 있어, U+1100 계열 현대 자모 시퀀스를 명시적으로 만든다.
        text = unicodedata.normalize("NFD", "안녕")
        # When
        result = normalize_korean(text)
        # Then
        self.assertEqual(result.text, "안녕")
        self.assertEqual(result.applied_rules, ("compose_modern_jamo",))

    def test_composes_compatibility_jamo(self) -> None:
        # Given
        text = "ㅇㅏㄴㄴㅕㅇ"
        # When
        result = normalize_korean(text)
        # Then
        self.assertEqual(result.text, "안녕")
        self.assertEqual(result.applied_rules, ("compose_compat_jamo",))

    def test_uses_following_vowel_as_next_syllable_boundary(self) -> None:
        # Given
        text = "ㄱㅏㄴㅏ"
        # When
        result = normalize_korean(text)
        # Then
        self.assertEqual(result.text, "가나")

    def test_composes_modern_jamo_syllable_without_trailing_final_consonant(self) -> None:
        # Given
        no_batchim = unicodedata.normalize("NFD", "가")
        # When
        result = normalize_korean(no_batchim)
        # Then
        self.assertEqual(result.text, "가")
        self.assertEqual(result.applied_rules, ("compose_modern_jamo",))

    def test_handles_composition_that_inserts_at_end_of_text(self) -> None:
        # Given
        text = "ㄱㅏ가"
        # When
        result = normalize_korean(text)
        # Then
        self.assertEqual(result.text, "가가")
        self.assertEqual(result.applied_rules, ("compose_compat_jamo",))

    def test_composes_after_removing_zwsp(self) -> None:
        # Given
        text = "ㅇ\u200bㅏ\u200bㄴ"
        # When
        result = normalize_korean(text)
        # Then
        self.assertEqual(result.text, "안")
        self.assertEqual(
            result.applied_rules,
            ("remove_hangul_zwsp", "compose_compat_jamo"),
        )

    def test_repeated_zwsp_edits_keep_original_offsets(self) -> None:
        # Given
        text = "가\u200b나\u200b다"
        # When
        result = normalize_korean(text)
        # Then
        self.assertEqual(result.text, "가나다")
        self.assertEqual(
            [
                (edit.source_start, edit.source_end, edit.before, edit.after)
                for edit in result.edits
            ],
            [(1, 2, "\u200b", ""), (3, 4, "\u200b", "")],
        )

    def test_preserves_non_hangul_zwsp_after_removed_neighbor(self) -> None:
        # Given
        text = "가\u200b\u200bA"
        # When
        result = normalize_korean(text)
        # Then
        self.assertEqual(result.text, "가\u200bA")
        self.assertEqual(len(result.edits), 1)
        self.assertEqual(
            (result.edits[0].source_start, result.edits[0].source_end),
            (1, 2),
        )

    def test_consecutive_compositions_remain_one_edit(self) -> None:
        # Given
        text = "ㅇㅏㄴㄴㅕㅇ"
        # When
        result = normalize_korean(text)
        # Then
        self.assertEqual(result.text, "안녕")
        self.assertEqual(len(result.edits), 1)
        self.assertEqual(
            (
                result.edits[0].source_start,
                result.edits[0].source_end,
                result.edits[0].before,
                result.edits[0].after,
            ),
            (0, 6, text, "안녕"),
        )

    def test_composition_spans_include_consumed_repeated_final(self) -> None:
        # Given
        cases = (
            ("ㅈㅏㅂㅂㅂㅎㅓ", "잡ㅂㅂ허"),
            ("잡ᆸᆸ허", "잡ᆸᆸ허"),
        )
        for text, expected in cases:
            with self.subTest(text=text):
                # When
                result = normalize_korean(text)
                # Then
                self.assertEqual(result.text, expected)
                self.assertEqual(
                    [
                        (edit.source_start, edit.source_end)
                        for edit in result.edits
                    ],
                    [(0, 3), (5, 7)],
                )
                self.assertEqual(result.edits[0].before, text[:3])
                self.assertEqual(result.edits[1].before, text[5:7])

    def test_long_repeated_zwsp_input_is_normalized(self) -> None:
        # Given
        syllable_count = 2_000
        text = "가\u200b" * syllable_count
        # When
        result = normalize_korean(text)
        # Then
        self.assertEqual(result.text, "가" * syllable_count)
        self.assertEqual(len(result.edits), syllable_count)
        self.assertEqual(result.edits[0].source_start, 1)
        self.assertEqual(result.edits[-1].source_end, len(text))

    def test_preserves_isolated_chosung(self) -> None:
        # Given
        text = "ㅇㅋ ㅋㅋ"
        # When
        result = normalize_korean(text)
        # Then
        self.assertEqual(result.text, "ㅇㅋ ㅋㅋ")
        self.assertFalse(result.changed)

    def test_preserves_punctuation_spacing_and_code_switching(self) -> None:
        # Given
        text = "[ㅇㅏㄴㄴㅕㅇ], API-v2!"
        # When
        result = normalize_korean(text)
        # Then
        self.assertEqual(result.text, "[안녕], API-v2!")

    def test_edit_span_uses_original_offsets(self) -> None:
        # Given
        text = "AㅇㅏB"
        # When
        result = normalize_korean(text)
        # Then
        self.assertEqual(len(result.edits), 1)
        edit = result.edits[0]
        self.assertEqual((edit.source_start, edit.source_end), (1, 3))
        self.assertEqual((edit.before, edit.after), ("ㅇㅏ", "아"))

    def test_empty_string_is_valid(self) -> None:
        # Given
        text = ""
        # When
        result = normalize_korean(text)
        # Then
        self.assertEqual(result.text, "")
        self.assertFalse(result.changed)
        self.assertEqual(result.errors, ())

    def test_rejects_non_string_input(self) -> None:
        # Given
        invalid_input = None
        # When / Then
        with self.assertRaisesRegex(TypeError, "str"):
            normalize_korean(invalid_input)  # type: ignore[arg-type]

    def test_is_deterministic(self) -> None:
        # Given
        text = "ㅇ\u200bㅏㄴㄴㅕㅇ, Guardrail"
        # When
        first_result = normalize_korean(text)
        second_result = normalize_korean(text)
        # Then
        self.assertEqual(first_result, second_result)


if __name__ == "__main__":
    unittest.main()
