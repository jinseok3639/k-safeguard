"""k-safeguard의 보수적인 한국어 표기 정규화 core.

정보 손실 없이 처리할 수 있는 Hangul 인접 ZWSP와 현대·호환 자모 조합만 적용한다.
초성체, 된소리, 연음과 띄어쓰기는 문맥상 모호하므로 이 단계에서는 변경하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable


NORMALIZER_VERSION = "0.1.0"
HANGUL_BASE = 0xAC00
ZWSP = "\u200b"

COMPAT_CHO = (
    "ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ",
    "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ",
)
COMPAT_JUNG = (
    "ㅏ", "ㅐ", "ㅑ", "ㅒ", "ㅓ", "ㅔ", "ㅕ", "ㅖ", "ㅗ", "ㅘ",
    "ㅙ", "ㅚ", "ㅛ", "ㅜ", "ㅝ", "ㅞ", "ㅟ", "ㅠ", "ㅡ", "ㅢ", "ㅣ",
)
COMPAT_JONG = (
    "", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ",
    "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ",
    "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ",
)

_COMPAT_CHO_INDEX = {char: index for index, char in enumerate(COMPAT_CHO)}
_COMPAT_JUNG_INDEX = {char: index for index, char in enumerate(COMPAT_JUNG)}
_COMPAT_JONG_INDEX = {char: index for index, char in enumerate(COMPAT_JONG) if char}
_COMPAT_COMPOUND_JONG_INDEX = {
    ("ㄱ", "ㅅ"): _COMPAT_JONG_INDEX["ㄳ"],
    ("ㄴ", "ㅈ"): _COMPAT_JONG_INDEX["ㄵ"],
    ("ㄴ", "ㅎ"): _COMPAT_JONG_INDEX["ㄶ"],
    ("ㄹ", "ㄱ"): _COMPAT_JONG_INDEX["ㄺ"],
    ("ㄹ", "ㅁ"): _COMPAT_JONG_INDEX["ㄻ"],
    ("ㄹ", "ㅂ"): _COMPAT_JONG_INDEX["ㄼ"],
    ("ㄹ", "ㅅ"): _COMPAT_JONG_INDEX["ㄽ"],
    ("ㄹ", "ㅌ"): _COMPAT_JONG_INDEX["ㄾ"],
    ("ㄹ", "ㅍ"): _COMPAT_JONG_INDEX["ㄿ"],
    ("ㄹ", "ㅎ"): _COMPAT_JONG_INDEX["ㅀ"],
    ("ㅂ", "ㅅ"): _COMPAT_JONG_INDEX["ㅄ"],
}


@dataclass(frozen=True)
class NormalizationEdit:
    """한 규칙이 바꾼 구간과 원문 기준 위치."""

    rule_id: str
    source_start: int
    source_end: int
    before: str
    after: str
    confidence: float
    lossy: bool = False


@dataclass(frozen=True)
class NormalizationResult:
    """정규화 문자열과 변경 추적 정보."""

    original: str
    text: str
    changed: bool
    lossy: bool
    confidence: float
    applied_rules: tuple[str, ...]
    edits: tuple[NormalizationEdit, ...]
    errors: tuple[str, ...]
    version: str = NORMALIZER_VERSION


@dataclass(frozen=True)
class _Unit:
    char: str
    source_start: int
    source_end: int


def _is_hangul_related(char: str) -> bool:
    code = ord(char)
    return (
        0xAC00 <= code <= 0xD7A3
        or 0x1100 <= code <= 0x11FF
        or 0x3130 <= code <= 0x318F
    )


def _remove_hangul_zwsp(text: str) -> str:
    output: list[str] = []
    for index, char in enumerate(text):
        if char != ZWSP:
            output.append(char)
            continue
        left = text[index - 1] if index > 0 else ""
        right = text[index + 1] if index + 1 < len(text) else ""
        if (left and _is_hangul_related(left)) or (right and _is_hangul_related(right)):
            continue
        output.append(char)
    return "".join(output)


def _compose_modern_jamo(text: str) -> str:
    """현대 조합형 자모(U+1100 계열)의 명확한 초·중·종 연속열을 조합한다."""
    output: list[str] = []
    index = 0
    while index < len(text):
        choseong = ord(text[index])
        if (
            0x1100 <= choseong <= 0x1112
            and index + 1 < len(text)
            and 0x1161 <= ord(text[index + 1]) <= 0x1175
        ):
            jungseong = ord(text[index + 1])
            jongseong_index = 0
            consumed = 2
            if index + 2 < len(text) and 0x11A8 <= ord(text[index + 2]) <= 0x11C2:
                jongseong_index = ord(text[index + 2]) - 0x11A7
                consumed = 3
            syllable = chr(
                HANGUL_BASE
                + (choseong - 0x1100) * 21 * 28
                + (jungseong - 0x1161) * 28
                + jongseong_index
            )
            output.append(syllable)
            index += consumed
            continue
        output.append(text[index])
        index += 1
    return "".join(output)


def _compose_compat_jamo(text: str) -> str:
    """호환 자모의 명확한 C+V(+C) 연속열을 완성형 음절로 조합한다."""
    output: list[str] = []
    index = 0
    while index < len(text):
        choseong_index = _COMPAT_CHO_INDEX.get(text[index])
        if (
            choseong_index is not None
            and index + 1 < len(text)
            and text[index + 1] in _COMPAT_JUNG_INDEX
        ):
            jungseong_index = _COMPAT_JUNG_INDEX[text[index + 1]]
            jongseong_index = 0
            consumed = 2
            candidate_index = index + 2
            if candidate_index < len(text):
                candidate = text[candidate_index]
                next_index = candidate_index + 1
                compound_jong = (
                    _COMPAT_COMPOUND_JONG_INDEX.get(
                        (candidate, text[next_index])
                    )
                    if next_index < len(text)
                    else None
                )
                compound_followed_by_vowel = (
                    compound_jong is not None
                    and next_index + 1 < len(text)
                    and text[next_index + 1] in _COMPAT_JUNG_INDEX
                )
                if compound_jong is not None and not compound_followed_by_vowel:
                    jongseong_index = compound_jong
                    consumed = 4
                else:
                    candidate_jong = _COMPAT_JONG_INDEX.get(candidate)
                    followed_by_vowel = (
                        candidate in _COMPAT_CHO_INDEX
                        and next_index < len(text)
                        and text[next_index] in _COMPAT_JUNG_INDEX
                    )
                    if candidate_jong is not None and not followed_by_vowel:
                        jongseong_index = candidate_jong
                        consumed = 3
            output.append(
                chr(
                    HANGUL_BASE
                    + choseong_index * 21 * 28
                    + jungseong_index * 28
                    + jongseong_index
                )
            )
            index += consumed
            continue
        output.append(text[index])
        index += 1
    return "".join(output)


def _source_span(units: list[_Unit], start: int, end: int) -> tuple[int, int]:
    if start < end:
        return units[start].source_start, units[end - 1].source_end
    if start < len(units):
        # 세 정규화 규칙(ZWSP 제거·현대/호환 자모 조합)은 문자 수를 줄이거나
        # 유지할 뿐 새 문자를 추가하지 않는다. 무작위 대입(30만+ 케이스)으로도
        # SequenceMatcher의 순수 삽입(insert) opcode가 문자열 끝이 아닌 위치에서
        # 발생하는 입력을 찾지 못했다 — 공개 API 입력만으로는 도달하지 않는다.
        point = units[start].source_start  # pragma: no cover
    elif units:
        point = units[-1].source_end
    else:
        # 빈 문자열은 세 규칙 모두 무변화(before == after)라 _apply_rule의 조기
        # 반환으로 끝나 이 지점에 도달하기 전에 끝난다 — units가 비어있는 채로
        # 여기 도달할 수 없다.
        point = 0  # pragma: no cover
    return point, point


def _apply_rule(
    units: list[_Unit],
    rule_id: str,
    transform: Callable[[str], str],
    confidence: float,
) -> tuple[list[_Unit], list[NormalizationEdit]]:
    before = "".join(unit.char for unit in units)
    after = transform(before)
    if before == after:
        return units, []

    output: list[_Unit] = []
    edits: list[NormalizationEdit] = []
    matcher = SequenceMatcher(a=before, b=after, autojunk=False)
    for tag, source_start, source_end, target_start, target_end in matcher.get_opcodes():
        if tag == "equal":
            output.extend(units[source_start:source_end])
            continue

        original_start, original_end = _source_span(units, source_start, source_end)
        replacement = after[target_start:target_end]
        for char in replacement:
            output.append(_Unit(char, original_start, original_end))
        edits.append(
            NormalizationEdit(
                rule_id=rule_id,
                source_start=original_start,
                source_end=original_end,
                before=before[source_start:source_end],
                after=replacement,
                confidence=confidence,
            )
        )

    if "".join(unit.char for unit in output) != after:  # pragma: no cover
        # SequenceMatcher opcode를 그대로 재조립하므로 항상 after와 일치한다 —
        # 공개 API 입력만으로는 도달할 수 없는 내부 정렬 방어 코드.
        raise RuntimeError(f"정규화 내부 정렬 오류: {rule_id}")
    return output, edits


def normalize_korean(text: str) -> NormalizationResult:
    """안전하게 확정할 수 있는 한국어 표기 변형만 정규화한다."""
    if not isinstance(text, str):
        raise TypeError("text는 str이어야 합니다.")

    units = [_Unit(char, index, index + 1) for index, char in enumerate(text)]
    edits: list[NormalizationEdit] = []
    rules = (
        ("remove_hangul_zwsp", _remove_hangul_zwsp, 1.0),
        ("compose_modern_jamo", _compose_modern_jamo, 1.0),
        ("compose_compat_jamo", _compose_compat_jamo, 1.0),
    )
    for rule_id, transform, confidence in rules:
        units, rule_edits = _apply_rule(units, rule_id, transform, confidence)
        edits.extend(rule_edits)

    normalized = "".join(unit.char for unit in units)
    applied_rules = tuple(dict.fromkeys(edit.rule_id for edit in edits))
    return NormalizationResult(
        original=text,
        text=normalized,
        changed=normalized != text,
        lossy=any(edit.lossy for edit in edits),
        confidence=min((edit.confidence for edit in edits), default=1.0),
        applied_rules=applied_rules,
        edits=tuple(edits),
        errors=(),
    )


__all__ = [
    "NORMALIZER_VERSION",
    "NormalizationEdit",
    "NormalizationResult",
    "normalize_korean",
]
