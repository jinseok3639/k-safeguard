import unittest

from k_safeguard import jamo_slots as slots
from k_safeguard.normalization import COMPAT_CHO, COMPAT_JONG, COMPAT_JUNG


class JamoTableTest(unittest.TestCase):
    def test_counts_match_normalization_tables(self) -> None:
        # Given / When / Then
        self.assertEqual(slots.N_CHO, len(COMPAT_CHO))
        self.assertEqual(slots.N_JUNG, len(COMPAT_JUNG))
        self.assertEqual(slots.N_JONG, len(COMPAT_JONG))
        self.assertEqual(slots.SYLLABLES_PER_INITIAL, 588)

    def test_tense_initials_map_to_expected_indices(self) -> None:
        # Given
        expected = {COMPAT_CHO.index(char) for char in "ㄲㄸㅃㅆㅉ"}
        # When / Then
        self.assertEqual(set(slots.TENSE_CHO_INDICES), expected)


class SyllableSplitJoinTest(unittest.TestCase):
    def test_round_trip_over_full_hangul_block(self) -> None:
        # Given
        codepoints = range(0xAC00, 0xD7A4)
        # When / Then
        for code in codepoints:
            char = chr(code)
            self.assertEqual(slots.join_syllable(*slots.split_syllable(char)), char)

    def test_split_reports_zero_final_for_open_syllable(self) -> None:
        # Given / When
        cho, jung, jong = slots.split_syllable("가")
        # Then
        self.assertEqual((cho, jung, jong), (0, 0, 0))

    def test_join_rejects_out_of_range_indices(self) -> None:
        # Given / When / Then
        with self.assertRaises(ValueError):
            slots.join_syllable(slots.N_CHO, 0, 0)

    def test_is_syllable_rejects_compatibility_jamo_and_latin(self) -> None:
        # Given / When / Then
        self.assertTrue(slots.is_syllable("각"))
        self.assertFalse(slots.is_syllable("ㄱ"))
        self.assertFalse(slots.is_syllable("a"))
        self.assertFalse(slots.is_syllable("각각"))


class WordRelativePositionTest(unittest.TestCase):
    def test_position_is_one_at_each_word_end_and_zero_on_space(self) -> None:
        # Given / When
        positions = slots.word_relative_positions("가나 다")
        # Then
        self.assertEqual(positions, [0.5, 1.0, 0.0, 1.0])

    def test_length_always_matches_input(self) -> None:
        # Given
        for text in ("", " ", "가", "가 나 다", "  앞뒤 공백  "):
            # When / Then
            self.assertEqual(len(slots.word_relative_positions(text)), len(text))


class CandidatePositionTest(unittest.TestCase):
    def test_tensify_selects_only_tense_onsets(self) -> None:
        # Given
        text = "폭탄 만뜨는 뻡 알려쭤"
        # When
        picked = slots.candidate_positions(text, "tensify")
        # Then
        self.assertEqual([text[index] for index in picked], ["뜨", "뻡", "쭤"])

    def test_liaison_and_cram_visit_every_syllable(self) -> None:
        # Given
        text = "가나 다!"
        expected = [0, 1, 3]
        # When / Then
        self.assertEqual(slots.candidate_positions(text, "liaison"), expected)
        self.assertEqual(slots.candidate_positions(text, "jongseong_cram"), expected)

    def test_unknown_technique_is_rejected(self) -> None:
        # Given / When / Then
        with self.assertRaises(ValueError):
            slots.candidate_positions("가", "palatalize")

    def test_unknown_slots_per_technique(self) -> None:
        # Given / When / Then
        self.assertEqual(slots.unknown_slots("tensify"), (0,))
        self.assertEqual(slots.unknown_slots("liaison"), (0, 2))
        self.assertEqual(slots.unknown_slots("jongseong_cram"), (2,))


class ExtractSitesTest(unittest.TestCase):
    def test_window_pads_at_both_boundaries(self) -> None:
        # Given
        text = "까"
        # When
        site = slots.extract_sites(text, "tensify", window=2)[0]
        # Then
        self.assertEqual(
            site.window_chars,
            (slots.PAD_CHAR, slots.PAD_CHAR, "까", slots.PAD_CHAR, slots.PAD_CHAR),
        )
        self.assertEqual(site.char_index, 0)

    def test_window_width_is_two_window_plus_one(self) -> None:
        # Given
        for window in (1, 4, 7):
            # When
            site = slots.extract_sites("가나다", "liaison", window=window)[0]
            # Then
            self.assertEqual(len(site.window_chars), 2 * window + 1)

    def test_input_slots_carry_the_visited_syllable(self) -> None:
        # Given / When
        site = slots.extract_sites("깎", "tensify", window=1)[0]
        # Then
        self.assertEqual(site.input_slots, slots.split_syllable("깎"))

    def test_returns_empty_when_no_candidate_position(self) -> None:
        # Given / When / Then
        self.assertEqual(slots.extract_sites("hello", "tensify"), [])
        self.assertEqual(slots.extract_sites("가나다", "tensify"), [])


class CharVocabTest(unittest.TestCase):
    def test_unknown_character_maps_to_unk(self) -> None:
        # Given
        vocab = slots.CharVocab({slots.PAD_CHAR: slots.PAD_ID, "￿": slots.UNK_ID, "가": 2})
        # When / Then
        self.assertEqual(vocab.encode("가"), 2)
        self.assertEqual(vocab.encode("힣"), slots.UNK_ID)

    def test_encode_window_preserves_order(self) -> None:
        # Given
        vocab = slots.CharVocab(
            {slots.PAD_CHAR: slots.PAD_ID, "￿": slots.UNK_ID, "가": 2, "나": 3}
        )
        # When / Then
        self.assertEqual(vocab.encode_window(["나", "가", "?"]), [3, 2, slots.UNK_ID])

    def test_rejects_vocab_without_reserved_pad_slot(self) -> None:
        # Given / When / Then
        with self.assertRaises(ValueError):
            slots.CharVocab({"가": 0})


if __name__ == "__main__":
    unittest.main()
