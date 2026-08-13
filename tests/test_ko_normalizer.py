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
        self.assertEqual(COMPAT_CHO, tuple(CHO))
        self.assertEqual(COMPAT_JUNG, tuple(JUNG))
        self.assertEqual(COMPAT_JONG, tuple(JONG))
        self.assertEqual(HANGUL_BASE, BASE)

    def test_clean_hangul_is_unchanged(self) -> None:
        result = normalize_korean("안녕하세요. Guardrail 테스트입니다.")
        self.assertEqual(result.text, result.original)
        self.assertFalse(result.changed)
        self.assertEqual(result.edits, ())
        self.assertEqual(result.confidence, 1.0)
        self.assertEqual(result.version, NORMALIZER_VERSION)

    def test_removes_zwsp_adjacent_to_hangul(self) -> None:
        result = normalize_korean("안\u200b녕\u200b하세요")
        self.assertEqual(result.text, "안녕하세요")
        self.assertEqual(result.applied_rules, ("remove_hangul_zwsp",))
        self.assertFalse(result.lossy)

    def test_preserves_non_hangul_zwsp(self) -> None:
        result = normalize_korean("abc\u200bdef")
        self.assertEqual(result.text, "abc\u200bdef")
        self.assertFalse(result.changed)

    def test_preserves_emoji_zwj_sequence(self) -> None:
        result = normalize_korean("개발자 👩\u200d💻")
        self.assertEqual(result.text, "개발자 👩\u200d💻")

    def test_composes_modern_jamo(self) -> None:
        result = normalize_korean("안녕")
        self.assertEqual(result.text, "안녕")
        self.assertEqual(result.applied_rules, ("compose_modern_jamo",))

    def test_composes_compatibility_jamo(self) -> None:
        result = normalize_korean("ㅇㅏㄴㄴㅕㅇ")
        self.assertEqual(result.text, "안녕")
        self.assertEqual(result.applied_rules, ("compose_compat_jamo",))

    def test_uses_following_vowel_as_next_syllable_boundary(self) -> None:
        self.assertEqual(normalize_korean("ㄱㅏㄴㅏ").text, "가나")

    def test_composes_modern_jamo_syllable_without_trailing_final_consonant(self) -> None:
        no_batchim = unicodedata.normalize("NFD", "가")
        result = normalize_korean(no_batchim)
        self.assertEqual(result.text, "가")
        self.assertEqual(result.applied_rules, ("compose_modern_jamo",))

    def test_handles_composition_that_inserts_at_end_of_text(self) -> None:
        result = normalize_korean("ㄱㅏ가")
        self.assertEqual(result.text, "가가")
        self.assertEqual(result.applied_rules, ("compose_compat_jamo",))

    def test_composes_after_removing_zwsp(self) -> None:
        result = normalize_korean("ㅇ\u200bㅏ\u200bㄴ")
        self.assertEqual(result.text, "안")
        self.assertEqual(
            result.applied_rules,
            ("remove_hangul_zwsp", "compose_compat_jamo"),
        )

    def test_preserves_isolated_chosung(self) -> None:
        result = normalize_korean("ㅇㅋ ㅋㅋ")
        self.assertEqual(result.text, "ㅇㅋ ㅋㅋ")
        self.assertFalse(result.changed)

    def test_preserves_punctuation_spacing_and_code_switching(self) -> None:
        result = normalize_korean("[ㅇㅏㄴㄴㅕㅇ], API-v2!")
        self.assertEqual(result.text, "[안녕], API-v2!")

    def test_edit_span_uses_original_offsets(self) -> None:
        result = normalize_korean("AㅇㅏB")
        self.assertEqual(len(result.edits), 1)
        edit = result.edits[0]
        self.assertEqual((edit.source_start, edit.source_end), (1, 3))
        self.assertEqual((edit.before, edit.after), ("ㅇㅏ", "아"))

    def test_empty_string_is_valid(self) -> None:
        result = normalize_korean("")
        self.assertEqual(result.text, "")
        self.assertFalse(result.changed)
        self.assertEqual(result.errors, ())

    def test_rejects_non_string_input(self) -> None:
        with self.assertRaisesRegex(TypeError, "str"):
            normalize_korean(None)  # type: ignore[arg-type]

    def test_is_deterministic(self) -> None:
        text = "ㅇ\u200bㅏㄴㄴㅕㅇ, Guardrail"
        self.assertEqual(normalize_korean(text), normalize_korean(text))


if __name__ == "__main__":
    unittest.main()
