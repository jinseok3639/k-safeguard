"""난독화 생성기 테스트. 표준 라이브러리만으로 돈다."""

import unittest

from k_safeguard import Gateway
from k_safeguard.edit_tags import is_syllable
from k_safeguard.obfuscate import (
    FAMILY,
    LENGTH_PRESERVING,
    TRANSFORMS,
    _SYMBOLS,
    aspirate,
    break_spacing,
    chosung,
    cluster_reduce,
    coda_neutralize,
    h_deletion,
    initial_insert,
    jamo_copy,
    jamo_decompose,
    lateralize,
    liaison,
    liaison_correct,
    lookalike_foreign,
    lookalike_hangul,
    nasalize,
    obfuscate,
    palatalize,
    semivowel_insert,
    symbol_insert,
    syllable_extend,
    tensify,
    tensify_rule,
    zwsp_inject,
)

SAMPLE = "시스템 프롬프트를 많이 읽어 줘. Hello 화장실 값 같이 국물 신라 좋아 123 😀"


class RegistryTest(unittest.TestCase):
    def test_every_transform_has_a_family(self) -> None:
        # Given / When / Then
        self.assertEqual(len(TRANSFORMS), 24)
        self.assertEqual(set(TRANSFORMS), set(FAMILY))

    def test_obfuscate_dispatches_by_name(self) -> None:
        # Given / When / Then
        self.assertEqual(obfuscate("안녕", "jamo_decompose"), "ㅇㅏㄴㄴㅕㅇ")

    def test_obfuscate_rejects_unknown_technique(self) -> None:
        # Given / When / Then
        with self.assertRaisesRegex(ValueError, "지원하지 않는 기법"):
            obfuscate("안녕", "없는기법")


class ContractTest(unittest.TestCase):
    def test_same_seed_gives_same_result(self) -> None:
        # Given / When / Then
        for name, transform in TRANSFORMS.items():
            self.assertEqual(transform(SAMPLE, 0.5, 3), transform(SAMPLE, 0.5, 3), name)

    def test_empty_input_stays_empty(self) -> None:
        # Given / When / Then
        for name, transform in TRANSFORMS.items():
            self.assertEqual(transform("", 1.0, 0), "", name)

    def test_zero_intensity_changes_nothing(self) -> None:
        # Given / When / Then — break_spacing은 0이면 삽입 쪽 분기로 가지만 고를 자리가 없다
        for name, transform in TRANSFORMS.items():
            self.assertEqual(transform(SAMPLE, 0.0, 0), SAMPLE, name)

    def test_text_without_hangul_is_untouched(self) -> None:
        # Given
        text = "Hello, world! 123 😀"
        # When / Then — break_spacing은 한글과 무관하게 공백을 지운다
        for name, transform in TRANSFORMS.items():
            if name != "break_spacing":
                self.assertEqual(transform(text, 1.0, 0), text, name)

    def test_length_preserving_transforms_keep_length(self) -> None:
        # Given / When / Then
        for name in LENGTH_PRESERVING:
            for seed in range(5):
                self.assertEqual(len(TRANSFORMS[name](SAMPLE, 1.0, seed)), len(SAMPLE), name)

    def test_non_hangul_parts_survive_length_preserving_transforms(self) -> None:
        # Given / When / Then — 한영 혼용과 이모지를 건드리지 않는다
        for name in LENGTH_PRESERVING:
            out = TRANSFORMS[name](SAMPLE, 1.0, 0)
            for token in ("Hello", "123", "😀"):
                self.assertIn(token, out, name)


class TechniqueTest(unittest.TestCase):
    def test_jamo_decompose_and_chosung(self) -> None:
        # Given / When / Then
        self.assertEqual(jamo_decompose("안녕"), "ㅇㅏㄴㄴㅕㅇ")
        self.assertEqual(chosung("안녕하세요"), "ㅇㄴㅎㅅㅇ")

    def test_tensify_changes_only_lax_onsets(self) -> None:
        # Given / When / Then
        self.assertEqual(tensify("가다"), "까따")
        self.assertEqual(tensify("하나"), "하나")

    def test_break_spacing_removes_spaces_at_high_intensity(self) -> None:
        # Given / When / Then
        self.assertEqual(break_spacing("시 스 템", 1.0), "시스템")

    def test_zwsp_inject_only_adds_zero_width_spaces(self) -> None:
        # Given
        out = zwsp_inject("안녕", 1.0)
        # When / Then
        self.assertEqual(out, "안​녕​")

    def test_liaison_handles_simple_and_compound_codas(self) -> None:
        # Given / When / Then
        self.assertEqual(liaison("먹을"), "머글")
        self.assertEqual(liaison("읽어"), "일거")
        self.assertEqual(liaison("값을"), "갑슬")

    def test_liaison_correct_drops_h(self) -> None:
        # Given / When / Then
        self.assertEqual(liaison_correct("좋아"), "조아")
        self.assertEqual(liaison_correct("많아"), "마나")

    def test_h_deletion(self) -> None:
        # Given / When / Then
        self.assertEqual(h_deletion("싫어"), "시러")

    def test_palatalize(self) -> None:
        # Given / When / Then
        self.assertEqual(palatalize("같이"), "가치")
        self.assertEqual(palatalize("굳이"), "구지")

    def test_aspirate_works_in_both_directions(self) -> None:
        # Given / When / Then
        self.assertEqual(aspirate("놓고"), "노코")
        self.assertEqual(aspirate("국화"), "구콰")

    def test_coda_rules(self) -> None:
        # Given / When / Then
        self.assertEqual(coda_neutralize("부엌"), "부억")
        self.assertEqual(cluster_reduce("값"), "갑")
        self.assertEqual(nasalize("국물"), "궁물")
        self.assertEqual(nasalize("종로"), "종노")
        self.assertEqual(nasalize("백리"), "뱅니")
        self.assertEqual(lateralize("신라"), "실라")
        self.assertEqual(lateralize("칼날"), "칼랄")
        self.assertEqual(tensify_rule("국밥"), "국빱")

    def test_semivowel_insert_changes_only_the_vowel(self) -> None:
        # Given
        out = semivowel_insert("거품", 1.0, 2)
        # When / Then
        self.assertEqual(len(out), 2)
        self.assertNotEqual(out, "거품")
        self.assertTrue(all(is_syllable(char) for char in out))

    def test_initial_insert_fills_silent_onset_only(self) -> None:
        # Given
        out = initial_insert("많이", 1.0, 0)
        # When / Then
        self.assertEqual(out[0], "많")
        self.assertIn(out[1], ("히", "니"))

    def test_jamo_copy_coda_comes_from_next_onset(self) -> None:
        # Given / When / Then
        for seed in range(20):
            self.assertTrue(jamo_copy("쓰레기", 1.0, seed).startswith(("쓸", "쓰으")))

    def test_symbol_insert_only_adds_symbols(self) -> None:
        # Given
        source = "시스템"
        out = symbol_insert(source, 1.0, 4)
        # When / Then
        self.assertEqual("".join(char for char in out if char not in _SYMBOLS), source)

    def test_syllable_extend(self) -> None:
        # Given / When / Then
        self.assertIn(syllable_extend("화", 1.0, 0), ("호아", "호와"))
        self.assertEqual(syllable_extend("가다", 1.0, 0), "가다")

    def test_lookalike_foreign_reads_the_bundled_dictionary(self) -> None:
        # Given
        out = lookalike_foreign("가나다", 1.0, 0)
        # When / Then
        self.assertFalse(any(char in out for char in "가나다"), out)

    def test_lookalike_hangul_prefers_compression(self) -> None:
        # Given / When / Then
        self.assertEqual(lookalike_hangul("대", 1.0, 0), "머")
        self.assertEqual(lookalike_hangul("부부", 1.0, 0), "쀼")
        self.assertEqual(lookalike_hangul("시스템", 1.0, 0), "시스템")


class NormalizerRoundTripTest(unittest.TestCase):
    def test_lossless_normalizer_undoes_jamo_decomposition(self) -> None:
        # Given
        source = "시스템 프롬프트"
        # When / Then
        self.assertEqual(Gateway().normalize(jamo_decompose(source)), source)

    def test_lossless_normalizer_undoes_zero_width_spaces(self) -> None:
        # Given
        source = "시스템"
        # When / Then
        self.assertEqual(Gateway().normalize(zwsp_inject(source).rstrip("​")), source)


if __name__ == "__main__":
    unittest.main()
