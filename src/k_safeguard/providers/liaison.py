"""발음대로 재음절화한 표기를 위한 bounded 연음 역변형 provider."""

from __future__ import annotations

from itertools import combinations
from typing import Iterator

from ..gateway import CandidateProposal


LIAISON_CANDIDATE_VERSION = "0.1.0"
_HANGUL_BASE = 0xAC00
_HANGUL_END = 0xD7A3
_SYLLABLES_PER_INITIAL = 21 * 28
_SILENT_INITIAL = 11  # ㅇ
_INITIAL_TO_FINAL = {
    0: 1,   # ㄱ
    1: 2,   # ㄲ
    2: 4,   # ㄴ
    3: 7,   # ㄷ
    5: 8,   # ㄹ
    6: 16,  # ㅁ
    7: 17,  # ㅂ
    9: 19,  # ㅅ
    10: 20,  # ㅆ
    12: 22,  # ㅈ
    14: 23,  # ㅊ
    15: 24,  # ㅋ
    16: 25,  # ㅌ
    17: 26,  # ㅍ
}


def _split_syllable(char: str) -> tuple[int, int, int]:
    offset = ord(char) - _HANGUL_BASE
    return (
        offset // _SYLLABLES_PER_INITIAL,
        (offset % _SYLLABLES_PER_INITIAL) // 28,
        offset % 28,
    )


def _join_syllable(initial: int, medial: int, final: int) -> str:
    return chr(
        _HANGUL_BASE
        + initial * _SYLLABLES_PER_INITIAL
        + medial * 28
        + final
    )


def _candidate_positions(text: str) -> tuple[int, ...]:
    positions: list[int] = []
    index = 0
    while index + 1 < len(text):
        left, right = text[index], text[index + 1]
        if (
            _HANGUL_BASE <= ord(left) <= _HANGUL_END
            and _HANGUL_BASE <= ord(right) <= _HANGUL_END
        ):
            _, _, left_final = _split_syllable(left)
            right_initial, _, _ = _split_syllable(right)
            if left_final == 0 and right_initial in _INITIAL_TO_FINAL:
                positions.append(index)
                index += 2
                continue
        index += 1
    return tuple(positions)


def _reverse_liaison(text: str, positions: tuple[int, ...]) -> str:
    output = list(text)
    for index in positions:
        left_initial, left_medial, _ = _split_syllable(text[index])
        right_initial, right_medial, right_final = _split_syllable(text[index + 1])
        output[index] = _join_syllable(
            left_initial,
            left_medial,
            _INITIAL_TO_FINAL[right_initial],
        )
        output[index + 1] = _join_syllable(
            _SILENT_INITIAL,
            right_medial,
            right_final,
        )
    return "".join(output)


class LiaisonInverseProvider:
    """단순 연음 표기를 가능한 원철자 후보로 되돌린다.

    ``머글게``에서 ``먹을게``처럼, 열린 음절 뒤의 평·경·격음 초성을 앞
    음절의 종성으로 옮기고 뒤 초성을 ``ㅇ``으로 바꾼다. 자연어에도 같은
    표면 패턴이 흔해 항상 lossy이며 기본 Gateway에는 연결되지 않는다.
    """

    name = "liaison_inverse"

    def __init__(self, *, max_candidates: int = 9, min_pairs: int = 1) -> None:
        if max_candidates < 1:
            raise ValueError("max_candidates는 1 이상이어야 합니다.")
        if min_pairs < 1:
            raise ValueError("min_pairs는 1 이상이어야 합니다.")
        self._max_candidates = max_candidates
        self._min_pairs = min_pairs

    def generate(self, text: str) -> Iterator[CandidateProposal]:
        if not isinstance(text, str):
            raise TypeError("text는 str이어야 합니다.")

        positions = _candidate_positions(text)
        if len(positions) < self._min_pairs:
            return

        emitted = 0
        for replacement_count in range(1, len(positions) + 1):
            for selected in combinations(positions, replacement_count):
                yield CandidateProposal(
                    text=_reverse_liaison(text, selected),
                    lossy=True,
                    confidence=None,
                    metadata=(
                        ("replacement_count", str(replacement_count)),
                        ("candidate_pairs", str(len(positions))),
                        ("min_pairs", str(self._min_pairs)),
                        ("source_positions", ",".join(map(str, selected))),
                        ("generator_version", LIAISON_CANDIDATE_VERSION),
                    ),
                )
                emitted += 1
                if emitted >= self._max_candidates:
                    return


__all__ = ["LIAISON_CANDIDATE_VERSION", "LiaisonInverseProvider"]
