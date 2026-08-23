import unittest

from hf_repo.ko_obfuscator import (
    BASE,
    COMPOUND_JONG_DECOMPOSITION,
    JONG,
    jamo_decompose,
)


class JamoDecomposeTest(unittest.TestCase):
    def test_decomposes_every_compound_final_into_keyboard_jamo(self) -> None:
        for compound, decomposed in COMPOUND_JONG_DECOMPOSITION.items():
            with self.subTest(compound=compound):
                syllable = chr(BASE + JONG.index(compound))  # ㄱ + ㅏ + 해당 종성
                self.assertEqual(
                    jamo_decompose(syllable),
                    f"ㄱㅏ{decomposed}",
                )

    def test_exposes_compound_final_normalization_cases(self) -> None:
        self.assertEqual(
            jamo_decompose("값이 없다 읽고"),
            "ㄱㅏㅂㅅㅇㅣ ㅇㅓㅂㅅㄷㅏ ㅇㅣㄹㄱㄱㅗ",
        )

    def test_can_reproduce_legacy_single_character_compound_final(self) -> None:
        self.assertEqual(
            jamo_decompose("값이", decompose_compound_finals=False),
            "ㄱㅏㅄㅇㅣ",
        )


if __name__ == "__main__":
    unittest.main()
