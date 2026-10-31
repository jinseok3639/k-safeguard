"""글자 편집 태거를 위한 의존성 없는 primitives.

복원 모델은 입력 글자마다 유지·삭제·음절 교체 중 하나와 "이 글자 앞에 공백을 넣을지"를
예측한다. 여기에는 모델 입력에 쓰는 자모 특징과, 모델 출력을 문자열로 되돌리는 규칙만
둔다. 표준 라이브러리만 쓰므로 extra 없이도 import·테스트된다. 실제 순전파(onnxruntime)와
토크나이저는 `providers/ml_restore.py`에서 다룬다.

자모 상수는 :mod:`k_safeguard.normalization`의 것을 그대로 재사용한다. 학습 때 쓴 인덱스와
하나만 어긋나도 조용히 틀린 결과가 나오므로 값을 복제하지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from .normalization import COMPAT_CHO, COMPAT_JONG, COMPAT_JUNG, HANGUL_BASE

EDIT_TAGS_VERSION = "1.0.0"

KEEP, DELETE, SUBSTITUTE = 0, 1, 2      # 모델 출력 순서. 학습 때 쓴 값과 반드시 같아야 한다.

HANGUL_END = 0xD7A3
_JUNG_COUNT = len(COMPAT_JUNG)
_JONG_COUNT = len(COMPAT_JONG)
_SYLLABLES_PER_INITIAL = _JUNG_COUNT * _JONG_COUNT

_CHO_INDEX = {char: index for index, char in enumerate(COMPAT_CHO)}
_JUNG_INDEX = {char: index for index, char in enumerate(COMPAT_JUNG)}
_JONG_INDEX = {char: index for index, char in enumerate(COMPAT_JONG) if char}
_SENTENCE_END = re.compile(r"[^.!?。\n]*(?:[.!?。\n]+\s*|$)")


def is_syllable(char: str) -> bool:
    """완성형 한글 음절인지."""
    return len(char) == 1 and HANGUL_BASE <= ord(char) <= HANGUL_END


def join_syllable(cho: int, jung: int, jong: int = 0) -> str:
    """(초성, 중성, 종성) 인덱스 -> 완성형 음절."""
    if not (0 <= cho < len(COMPAT_CHO) and 0 <= jung < _JUNG_COUNT and 0 <= jong < _JONG_COUNT):
        raise ValueError(f"자모 인덱스 범위를 벗어났습니다: ({cho}, {jung}, {jong})")
    return chr(HANGUL_BASE + cho * _SYLLABLES_PER_INITIAL + jung * _JONG_COUNT + jong)


def jamo_features(char: str) -> tuple[int, int, int]:
    """모델 입력용 (초, 중, 종) 인덱스 + 1. 0은 '없음'. 낱자 자모는 해당 슬롯 하나만 채운다.

    초성과 종성에 다 있는 자음(ㄱ 등)은 초성으로 본다. 학습 때와 같은 순서다.
    """
    if is_syllable(char):
        code = ord(char) - HANGUL_BASE
        return (
            code // _SYLLABLES_PER_INITIAL + 1,
            (code % _SYLLABLES_PER_INITIAL) // _JONG_COUNT + 1,
            code % _JONG_COUNT + 1,
        )
    if char in _CHO_INDEX:
        return _CHO_INDEX[char] + 1, 0, 0
    if char in _JUNG_INDEX:
        return 0, _JUNG_INDEX[char] + 1, 0
    if char in _JONG_INDEX:
        return 0, 0, _JONG_INDEX[char] + 1
    return 0, 0, 0


def split_chunks(text: str, max_chars: int, limit: int | None = None) -> list[str]:
    """`text`를 `max_chars` 이하 조각으로 나눈다. 이어 붙이면 항상 원문과 같다.

    문장 끝에서 나누고, 한 문장이 너무 길면 공백에서, 공백도 없으면 글자 수로 자른다.
    `limit`을 주면 그만큼 모은 뒤 멈춘다. 이때 조각을 이어 붙이면 원문의 앞부분과 같고, 뒤를
    더 읽지 않으므로 신뢰할 수 없는 긴 입력에서도 비용이 늘지 않는다.
    """
    if max_chars < 1:
        raise ValueError("max_chars는 1 이상이어야 합니다.")
    if limit is not None and limit < 1:
        raise ValueError("limit은 1 이상이어야 합니다.")
    chunks: list[str] = []
    current = ""
    for match in _SENTENCE_END.finditer(text):
        sentence = match.group()
        if len(current) + len(sentence) <= max_chars:
            current += sentence
            continue
        if current:
            chunks.append(current)
            if len(chunks) == limit:
                return chunks
        start = 0
        while len(sentence) - start > max_chars:
            cut = sentence.rfind(" ", start + 1, start + max_chars) + 1 or start + max_chars
            chunks.append(sentence[start:cut])
            if len(chunks) == limit:
                return chunks
            start = cut
        current = sentence[start:]
    if current:
        chunks.append(current)
    return chunks


@dataclass(frozen=True)
class CharEdit:
    """글자 하나에 대한 모델 예측(기권 전)."""

    op: int = KEEP
    replacement: str = ""       # op가 SUBSTITUTE일 때만 쓴다
    confidence: float = 1.0
    space_confidence: float = 0.0


def apply_edits(
    text: str, edits: Sequence[CharEdit], threshold: float
) -> tuple[str, int, float]:
    """확신도가 `threshold` 이상인 편집만 적용한다. (복원문, 적용한 편집 수, 평균 확신도).

    임계값에 못 미친 글자는 입력을 그대로 둔다(abstention). 앞 공백은 0.5 미만이면 임계값이
    낮아도 넣지 않는다. 모델이 "공백 없음"을 더 높게 본 자리이기 때문이다.
    """
    if len(edits) != len(text):
        raise ValueError(f"편집 수({len(edits)})가 글자 수({len(text)})와 다릅니다.")
    output: list[str] = []
    applied: list[float] = []
    space_bar = max(threshold, 0.5)
    for char, edit in zip(text, edits):
        if edit.space_confidence >= space_bar:
            output.append(" ")
            applied.append(edit.space_confidence)
        if edit.op == KEEP or edit.confidence < threshold:
            output.append(char)
            continue
        applied.append(edit.confidence)
        if edit.op == SUBSTITUTE:
            output.append(edit.replacement)
    if not applied:
        return text, 0, 0.0
    return "".join(output), len(applied), sum(applied) / len(applied)


__all__ = [
    "DELETE",
    "EDIT_TAGS_VERSION",
    "KEEP",
    "SUBSTITUTE",
    "CharEdit",
    "apply_edits",
    "is_syllable",
    "jamo_features",
    "join_syllable",
    "split_chunks",
]
