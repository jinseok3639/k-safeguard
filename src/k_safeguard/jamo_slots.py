"""자모 슬롯 복원기를 위한 의존성 없는 primitives.

완성형 음절을 초성·중성·종성 세 슬롯으로 나누고, 기법별로 "복원 후보가 될 수 있는
위치"를 고르고, 그 위치 주변의 문자 창을 모델 입력 배열로 인코딩한다.

`chosung.py`와 같은 위치에 두는 이유도 같다 — provider와 무관한 순수 계산이라
따로 테스트할 수 있어야 하고, 표준 라이브러리만 쓰므로 extra 없이도 import된다.
실제 순전파(onnxruntime)만 `providers/ml_restore.py`에서 다룬다.

자모 상수는 :mod:`k_safeguard.normalization`의 것을 그대로 재사용한다. 값을 복제하면
두 벌이 갈라질 수 있고, 정규화기와 복원기가 같은 자모 테이블을 본다는 보장이 깨진다.

## 후보 위치 규칙

복원 모델은 문장 전체를 다시 쓰지 않는다. 아래 규칙이 고른 위치만 방문해서 그 자리의
"모르는 슬롯"을 예측하고, 나머지는 입력을 그대로 복사한다. 규칙은 **난독화된 입력만
보고** 정할 수 있어야 한다 — 정답을 봐야 알 수 있는 규칙을 쓰면 학습 때만 좋아 보이고
실제 추론에서는 쓸 수 없다.

- ``tensify`` — 경음 초성(ㄲㄸㅃㅆㅉ)을 가진 음절. 된소리화는 반드시 이 다섯 자음 중
  하나를 남기므로 좁게 고를 수 있다.
- ``liaison`` — 모든 음절. 연음의 결과물은 문법적으로 정상인 한글이라 값싼 신호가 없다.
- ``jongseong_cram`` — 모든 음절. 같은 이유.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from .normalization import COMPAT_CHO, COMPAT_JONG, COMPAT_JUNG, HANGUL_BASE

JAMO_SLOTS_VERSION = "0.1.0"

HANGUL_END = 0xD7A3
JUNG_COUNT = len(COMPAT_JUNG)          # 21
JONG_COUNT = len(COMPAT_JONG)          # 28
SYLLABLES_PER_INITIAL = JUNG_COUNT * JONG_COUNT   # 588

N_CHO = len(COMPAT_CHO)                # 19
N_JUNG = JUNG_COUNT                    # 21
N_JONG = JONG_COUNT                    # 28

CHO_INDEX = {char: index for index, char in enumerate(COMPAT_CHO)}

TENSE_TO_LAX = {"ㄲ": "ㄱ", "ㄸ": "ㄷ", "ㅃ": "ㅂ", "ㅆ": "ㅅ", "ㅉ": "ㅈ"}
TENSE_CHO_INDICES = frozenset(CHO_INDEX[char] for char in TENSE_TO_LAX)

# 문자 창 인코딩의 예약 id. 학습 때 쓴 값과 반드시 같아야 한다.
PAD_ID = 0
UNK_ID = 1
PAD_CHAR = "\x00"


def is_syllable(char: str) -> bool:
    """완성형 한글 음절인지."""
    return len(char) == 1 and HANGUL_BASE <= ord(char) <= HANGUL_END


def split_syllable(char: str) -> tuple[int, int, int]:
    """완성형 음절 -> (초성, 중성, 종성) 인덱스. 종성 0은 받침 없음."""
    code = ord(char) - HANGUL_BASE
    return (
        code // SYLLABLES_PER_INITIAL,
        (code % SYLLABLES_PER_INITIAL) // JONG_COUNT,
        code % JONG_COUNT,
    )


def join_syllable(cho: int, jung: int, jong: int = 0) -> str:
    """(초성, 중성, 종성) 인덱스 -> 완성형 음절."""
    if not (0 <= cho < N_CHO and 0 <= jung < N_JUNG and 0 <= jong < N_JONG):
        raise ValueError(f"자모 인덱스 범위를 벗어났습니다: ({cho}, {jung}, {jong})")
    return chr(HANGUL_BASE + cho * SYLLABLES_PER_INITIAL + jung * JONG_COUNT + jong)


def word_relative_positions(text: str) -> list[float]:
    """각 문자의 어절 내 상대 위치(0 < v <= 1). 공백은 0.0.

    모델이 쓰는 유일한 어절 수준 신호다. 어절 경계는 공백 기준으로만 잡는다.
    """
    out = [0.0] * len(text)
    start = None
    for index, char in enumerate(text + " "):
        if index == len(text) or char.isspace():
            if start is not None:
                span = index - start
                for position in range(start, index):
                    out[position] = round((position - start + 1) / span, 4)
                start = None
        elif start is None:
            start = index
    return out


def _all_syllables(text: str) -> list[int]:
    return [index for index, char in enumerate(text) if is_syllable(char)]


def _onset_in(indices: frozenset[int]) -> Callable[[str], list[int]]:
    def rule(text: str) -> list[int]:
        return [
            index
            for index, char in enumerate(text)
            if is_syllable(char) and split_syllable(char)[0] in indices
        ]

    return rule


# technique -> (모르는 슬롯, 후보 위치 규칙). 슬롯은 (초성, 중성, 종성) = (0, 1, 2).
# 나머지 슬롯은 입력에서 그대로 복사한다.
TECHNIQUE_SPEC: dict[str, tuple[tuple[int, ...], Callable[[str], list[int]]]] = {
    "tensify": ((0,), _onset_in(TENSE_CHO_INDICES)),
    "liaison": ((0, 2), _all_syllables),
    "jongseong_cram": ((2,), _all_syllables),
}

SUPPORTED_TECHNIQUES = tuple(sorted(TECHNIQUE_SPEC))


def unknown_slots(technique: str) -> tuple[int, ...]:
    """해당 기법에서 모델이 예측해야 하는 슬롯."""
    return _spec(technique)[0]


def candidate_positions(text: str, technique: str) -> list[int]:
    """입력만 보고 고른 후보 위치. 학습과 추론이 반드시 같은 규칙을 써야 한다."""
    return _spec(technique)[1](text)


def _spec(technique: str) -> tuple[tuple[int, ...], Callable[[str], list[int]]]:
    try:
        return TECHNIQUE_SPEC[technique]
    except KeyError:
        raise ValueError(
            f"지원하지 않는 기법입니다: {technique!r} "
            f"(사용 가능: {', '.join(SUPPORTED_TECHNIQUES)})"
        ) from None


@dataclass(frozen=True)
class SlotSite:
    """복원 모델이 방문하는 자리 하나."""

    char_index: int
    window_chars: tuple[str, ...]
    rel_position: float
    input_slots: tuple[int, int, int]   # 모르는 자리는 -1


def _slots_of(char: str) -> tuple[int, int, int]:
    if is_syllable(char):
        return split_syllable(char)
    if char in CHO_INDEX:
        return (CHO_INDEX[char], -1, -1)     # 초성체 낱자: 초성만 알려짐
    return (-1, -1, -1)


def extract_sites(text: str, technique: str, window: int = 4) -> list[SlotSite]:
    """문자열 하나에서 후보 자리를 뽑는다.

    정답(clean 원문) 없이 난독화된 입력만 받는다 — 추론 시점에는 정답이 없고,
    학습 경로를 추론에 끌어오면 난독화 생성기까지 딸려 오기 때문이다.
    """
    positions = candidate_positions(text, technique)
    if not positions:
        return []
    relative = word_relative_positions(text)
    return [
        SlotSite(
            char_index=index,
            window_chars=tuple(
                text[index + offset] if 0 <= index + offset < len(text) else PAD_CHAR
                for offset in range(-window, window + 1)
            ),
            rel_position=relative[index],
            input_slots=_slots_of(text[index]),
        )
        for index in positions
    ]


class CharVocab:
    """문자 -> id. 학습 때 만든 사전을 그대로 읽어 쓰고, 미등록 문자는 UNK로 보낸다."""

    def __init__(self, ids: dict[str, int]) -> None:
        if ids.get(PAD_CHAR) != PAD_ID:
            raise ValueError(f"vocab의 PAD 항목이 {PAD_ID}이 아닙니다.")
        self._ids = dict(ids)

    def __len__(self) -> int:
        return len(self._ids)

    def encode(self, char: str) -> int:
        return self._ids.get(char, UNK_ID)

    def encode_window(self, chars: Sequence[str]) -> list[int]:
        return [self.encode(char) for char in chars]


def encode_sites(sites: Iterable[SlotSite], vocab: CharVocab):
    """자리 목록 -> 모델 입력 배열 (문자 id 창, 어절 상대 위치, 입력 자모 슬롯).

    numpy가 필요하므로 `k-safeguard[ml-restore]` 없이는 쓸 수 없다. 위쪽 함수들은
    전부 표준 라이브러리만 쓴다.
    """
    import numpy as np

    sites = list(sites)
    if not sites:
        raise ValueError("인코딩할 자리가 없습니다.")
    width = len(sites[0].window_chars)
    chars = np.zeros((len(sites), width), dtype=np.int64)
    positions = np.zeros((len(sites), 1), dtype=np.float32)
    slots = np.zeros((len(sites), 3), dtype=np.int64)
    # 모르는 슬롯(-1)은 각 슬롯의 클래스 수를 sentinel 인덱스로 쓴다 — 학습과 동일.
    sentinels = (N_CHO, N_JUNG, N_JONG)
    for row, site in enumerate(sites):
        chars[row] = vocab.encode_window(site.window_chars)
        positions[row, 0] = site.rel_position
        slots[row] = [
            value if value >= 0 else sentinel
            for value, sentinel in zip(site.input_slots, sentinels)
        ]
    return chars, positions, slots


__all__ = [
    "CHO_INDEX",
    "JAMO_SLOTS_VERSION",
    "N_CHO",
    "N_JONG",
    "N_JUNG",
    "PAD_CHAR",
    "PAD_ID",
    "SUPPORTED_TECHNIQUES",
    "TENSE_CHO_INDICES",
    "UNK_ID",
    "CharVocab",
    "SlotSite",
    "candidate_positions",
    "encode_sites",
    "extract_sites",
    "is_syllable",
    "join_syllable",
    "split_syllable",
    "unknown_slots",
    "word_relative_positions",
]
