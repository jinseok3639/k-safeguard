"""과거 된소리 다중 view 실험을 재현하기 위한 내부 provider."""

from __future__ import annotations

from itertools import combinations
from typing import Iterator

from ..gateway import CandidateProposal


TENSIFY_CANDIDATE_VERSION = "0.3.0"
DEFAULT_TENSIFY_DIVERSIFY_FROM = 17
_HANGUL_BASE = 0xAC00
_HANGUL_END = 0xD7A3
_SYLLABLES_PER_INITIAL = 21 * 28
_TENSE_TO_LAX = {
    1: 0,   # ㄲ -> ㄱ
    4: 3,   # ㄸ -> ㄷ
    8: 7,   # ㅃ -> ㅂ
    10: 9,  # ㅆ -> ㅅ
    13: 12,  # ㅉ -> ㅈ
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


def _replacement_count_order(total: int) -> tuple[int, ...]:
    """작은/큰 치환 tier를 번갈아 반환해 한쪽 극단의 독점을 막는다."""
    order: list[int] = []
    low, high = 1, total - 1
    while low <= high:
        order.append(low)
        if high != low:
            order.append(high)
        low += 1
        high -= 1
    return tuple(order)


def _legacy_position_sets(positions: tuple[int, ...]) -> Iterator[tuple[int, ...]]:
    """검증된 기존 정책: 치환 개수가 많은 조합부터 지연 생성한다."""
    for replacement_count in range(len(positions), 0, -1):
        yield from combinations(positions, replacement_count)


def _diverse_position_sets(positions: tuple[int, ...]) -> Iterator[tuple[int, ...]]:
    """전부 복원 후 치환 개수 tier를 round-robin으로 지연 생성한다."""
    yield positions
    iterators = []
    for replacement_count in _replacement_count_order(len(positions)):
        iterator = iter(combinations(positions, replacement_count))
        yield next(iterator)
        iterators.append(iterator)

    while iterators:
        remaining = []
        for iterator in iterators:
            try:
                yield next(iterator)
                remaining.append(iterator)
            except StopIteration:
                pass
        iterators = remaining


class TensifyInverseProvider:
    """된소리 초성을 평음으로 되돌린 제한된 lossy view를 생성한다.

    원문 view는 :class:`~k_safeguard.gateway.Gateway`가 항상 보존한다. 후보는
    첫 후보는 모든 위치를 복원해 강한 된소리화 공격을 먼저 검사한다. 경음 위치 수가
    ``diversify_from``보다 작으면 검증된 기존 순서를 유지한다. 임계치 이상의 긴 입력만
    치환 개수 1·(n-1)·2·(n-2)… tier를 round-robin해 한쪽 극단의 근사 중복이
    view 예산을 독점하지 않게 한다. 같은 치환 개수에서는 왼쪽 위치 조합을 우선한다.
    """

    name = "tensify_inverse"

    def __init__(
        self,
        *,
        max_candidates: int = 9,
        min_tense_syllables: int = 1,
        min_tense_ratio: float = 0.0,
        diversify_from: int = DEFAULT_TENSIFY_DIVERSIFY_FROM,
    ) -> None:
        if max_candidates < 1:
            raise ValueError("max_candidates는 1 이상이어야 합니다.")
        if min_tense_syllables < 1:
            raise ValueError("min_tense_syllables는 1 이상이어야 합니다.")
        if not 0.0 <= min_tense_ratio <= 1.0:
            raise ValueError("min_tense_ratio는 0~1이어야 합니다.")
        if diversify_from < 2:
            raise ValueError("diversify_from은 2 이상이어야 합니다.")
        self._max_candidates = max_candidates
        self._min_tense_syllables = min_tense_syllables
        self._min_tense_ratio = min_tense_ratio
        self._diversify_from = diversify_from

    def generate(self, text: str) -> Iterator[CandidateProposal]:
        if not isinstance(text, str):
            raise TypeError("text는 str이어야 합니다.")

        positions = _tense_positions(text)
        hangul_syllables = sum(
            _HANGUL_BASE <= ord(char) <= _HANGUL_END for char in text
        )
        tense_ratio = len(positions) / hangul_syllables if hangul_syllables else 0.0
        if (
            len(positions) < self._min_tense_syllables
            or tense_ratio < self._min_tense_ratio
        ):
            return

        position_sets = (
            _diverse_position_sets(positions)
            if len(positions) >= self._diversify_from
            else _legacy_position_sets(positions)
        )
        for emitted, selected in enumerate(position_sets, start=1):
            yield CandidateProposal(
                text=_detensify(text, selected),
                lossy=True,
                confidence=None,
                metadata=(
                    ("replacement_count", str(len(selected))),
                    ("total_tense_syllables", str(len(positions))),
                    ("total_hangul_syllables", str(hangul_syllables)),
                    ("tense_ratio", f"{tense_ratio:.6f}"),
                    ("min_tense_syllables", str(self._min_tense_syllables)),
                    ("min_tense_ratio", f"{self._min_tense_ratio:.6f}"),
                    ("diversify_from", str(self._diversify_from)),
                    ("source_positions", ",".join(map(str, selected))),
                    ("generator_version", TENSIFY_CANDIDATE_VERSION),
                ),
            )
            if emitted >= self._max_candidates:
                return


__all__: list[str] = []
