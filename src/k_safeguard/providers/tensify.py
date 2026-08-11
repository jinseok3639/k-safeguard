"""된소리화된 완성형 한글을 위한 bounded 역변형 후보 provider."""

from __future__ import annotations

from itertools import combinations
from typing import Iterator

from ..gateway import CandidateProposal


TENSIFY_CANDIDATE_VERSION = "0.1.0"
_HANGUL_BASE = 0xAC00
_HANGUL_END = 0xD7A3
_SYLLABLES_PER_INITIAL = 21 * 28
_TENSE_TO_LAX = {
    1: 0,   # ㄲ -> ㄱ
    4: 3,   # ㄸ -> ㄷ
    8: 7,   # ㅃ -> ㅂ
    10: 9,  # ㅆ -> ㅅ
    13: 12, # ㅉ -> ㅈ
}


def _tense_positions(text: str) -> tuple[int, ...]:
    positions: list[int] = []
    for index, char in enumerate(text):
        code = ord(char)
        if not _HANGUL_BASE <= code <= _HANGUL_END:
            continue
        initial = (code - _HANGUL_BASE) // _SYLLABLES_PER_INITIAL
        if initial in _TENSE_TO_LAX:
            positions.append(index)
    return tuple(positions)


def _detensify(text: str, positions: tuple[int, ...]) -> str:
    output = list(text)
    for index in positions:
        syllable_offset = ord(output[index]) - _HANGUL_BASE
        initial = syllable_offset // _SYLLABLES_PER_INITIAL
        output[index] = chr(
            _HANGUL_BASE
            + _TENSE_TO_LAX[initial] * _SYLLABLES_PER_INITIAL
            + syllable_offset % _SYLLABLES_PER_INITIAL
        )
    return "".join(output)


class TensifyInverseProvider:
    """된소리 초성을 평음으로 되돌린 제한된 lossy view를 생성한다.

    원문 view는 :class:`~k_safeguard.gateway.Gateway`가 항상 보존한다. 후보는
    복원 위치가 많은 순서로 생성해 강한 된소리화 공격을 작은 view 예산에서 먼저
    검사하며, 같은 복원 개수에서는 왼쪽 위치 조합을 우선한다.
    """

    name = "tensify_inverse"

    def __init__(self, *, max_candidates: int = 9) -> None:
        if max_candidates < 1:
            raise ValueError("max_candidates는 1 이상이어야 합니다.")
        self._max_candidates = max_candidates

    def generate(self, text: str) -> Iterator[CandidateProposal]:
        if not isinstance(text, str):
            raise TypeError("text는 str이어야 합니다.")

        positions = _tense_positions(text)
        emitted = 0
        for replacement_count in range(len(positions), 0, -1):
            for selected in combinations(positions, replacement_count):
                yield CandidateProposal(
                    text=_detensify(text, selected),
                    lossy=True,
                    confidence=None,
                    metadata=(
                        ("replacement_count", str(replacement_count)),
                        ("total_tense_syllables", str(len(positions))),
                        ("source_positions", ",".join(map(str, selected))),
                        ("generator_version", TENSIFY_CANDIDATE_VERSION),
                    ),
                )
                emitted += 1
                if emitted >= self._max_candidates:
                    return


__all__ = ["TENSIFY_CANDIDATE_VERSION", "TensifyInverseProvider"]
