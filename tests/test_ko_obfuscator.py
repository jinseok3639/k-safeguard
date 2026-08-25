import json
import unittest
from collections import Counter
from pathlib import Path

from experiments.benchmark.run_normalizer_evaluation import FAMILY_MAP, LOSSY_TECHNIQUES
from hf_repo.ko_obfuscator import (
    BASE,
    COMPOUND_JONG_DECOMPOSITION,
    JONG,
    TRANSFORMS,
    _split,
    final_insertion,
    final_near_sound,
    jamo_decompose,
    liaison,
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


class FinalInsertionTest(unittest.TestCase):
    def test_inserts_finals_only_into_open_syllables(self) -> None:
        original = "가나다 각"

        transformed = final_insertion(original, intensity=1.0, seed=42)

        self.assertNotEqual(transformed, original)
        self.assertEqual(transformed[-1], "각")
        for before, after in zip(original[:3], transformed[:3]):
            before_c, before_j, before_t = _split(before)
            after_c, after_j, after_t = _split(after)
            self.assertEqual((after_c, after_j), (before_c, before_j))
            self.assertEqual(before_t, 0)
            self.assertNotEqual(after_t, 0)

    def test_is_deterministic_and_zero_intensity_is_identity(self) -> None:
        text = "한국어 테스트"

        self.assertEqual(
            final_insertion(text, intensity=0.5, seed=2026),
            final_insertion(text, intensity=0.5, seed=2026),
        )
        self.assertEqual(final_insertion(text, intensity=0.0, seed=2026), text)


class FinalNearSoundTest(unittest.TestCase):
    def test_replaces_only_registered_near_sound_finals(self) -> None:
        self.assertEqual(
            final_near_sound("밖 옷 빛 앞 한 말 밤 공", intensity=1.0, seed=7),
            "박 옫 빋 압 한 말 밤 공",
        )

    def test_is_deterministic_and_zero_intensity_is_identity(self) -> None:
        text = "입력값을 출력"

        self.assertEqual(
            final_near_sound(text, intensity=0.5, seed=17),
            final_near_sound(text, intensity=0.5, seed=17),
        )
        self.assertEqual(final_near_sound(text, intensity=0.0, seed=17), text)


class LiaisonTest(unittest.TestCase):
    def test_moves_simple_final_to_silent_onset(self) -> None:
        self.assertEqual(liaison("먹을게", intensity=1.0, seed=42), "머글게")
        self.assertEqual(liaison("꽃이", intensity=1.0, seed=42), "꼬치")

    def test_excludes_clusters_ng_hieuh_and_space_boundaries(self) -> None:
        text = "값이 강아지 좋아 먹 어"

        self.assertEqual(liaison(text, intensity=1.0, seed=42), text)

    def test_overlapping_pairs_are_not_applied_twice(self) -> None:
        self.assertEqual(liaison("각악아", intensity=1.0, seed=42), "가각아")

    def test_is_deterministic_and_zero_intensity_is_identity(self) -> None:
        text = "먹어서 확인"

        self.assertEqual(
            liaison(text, intensity=0.5, seed=1234),
            liaison(text, intensity=0.5, seed=1234),
        )
        self.assertEqual(liaison(text, intensity=0.0, seed=1234), text)


class TransformRegistryTest(unittest.TestCase):
    def test_registers_o2_and_p3_as_separate_techniques(self) -> None:
        self.assertIs(TRANSFORMS["final_insertion"], final_insertion)
        self.assertIs(TRANSFORMS["final_near_sound"], final_near_sound)
        self.assertIs(TRANSFORMS["liaison"], liaison)

    def test_evaluation_metadata_marks_new_techniques_as_lossy(self) -> None:
        self.assertEqual(FAMILY_MAP["final_insertion"], "orthographic")
        self.assertEqual(FAMILY_MAP["final_near_sound"], "orthographic")
        self.assertEqual(FAMILY_MAP["liaison"], "phonetic")
        self.assertTrue(
            {"final_insertion", "final_near_sound", "liaison"}
            <= LOSSY_TECHNIQUES
        )


class BenchmarkArtifactTest(unittest.TestCase):
    def test_checked_benchmark_contains_every_registered_transform(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        benchmark_path = repo_root / "hf_repo" / "benchmark.jsonl"
        seed_count = sum(
            1
            for path in (repo_root / "hf_repo" / "seeds").glob("*.jsonl")
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        technique_counts = Counter(
            json.loads(line)["technique"]
            for line in benchmark_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )

        self.assertEqual(technique_counts["clean"], seed_count)
        self.assertEqual(set(technique_counts) - {"clean"}, set(TRANSFORMS))
        for technique in TRANSFORMS:
            with self.subTest(technique=technique):
                self.assertEqual(technique_counts[technique], seed_count * 2)


if __name__ == "__main__":
    unittest.main()
