"""k-safeguard의 보수적인 한국어 표기 정규화 core.

정보 손실 없이 처리할 수 있는 Hangul 인접 ZWSP와 현대·호환 자모 조합만 적용한다.
초성체, 된소리, 연음과 띄어쓰기는 문맥상 모호하므로 이 단계에서는 변경하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass


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


def _make_edit(
    rule_id: str,
    source_units: list[_Unit],
    after: str,
) -> NormalizationEdit:
    return NormalizationEdit(
        rule_id=rule_id,
        source_start=source_units[0].source_start,
        source_end=source_units[-1].source_end,
        before="".join(unit.char for unit in source_units),
        after=after,
        confidence=1.0,
    )


def _remove_hangul_zwsp(
    units: list[_Unit],
) -> tuple[list[_Unit], list[NormalizationEdit]]:
    output: list[_Unit] = []
    edits: list[NormalizationEdit] = []
    removed_run: list[_Unit] = []

    for index, unit in enumerate(units):
        if unit.char != ZWSP:
            if removed_run:
                edits.append(_make_edit("remove_hangul_zwsp", removed_run, ""))
                removed_run = []
            output.append(unit)
            continue
        left = units[index - 1].char if index > 0 else ""
        right = units[index + 1].char if index + 1 < len(units) else ""
        if (left and _is_hangul_related(left)) or (right and _is_hangul_related(right)):
            removed_run.append(unit)
            continue
        if removed_run:
            edits.append(_make_edit("remove_hangul_zwsp", removed_run, ""))
            removed_run = []
        output.append(unit)

    if removed_run:
        edits.append(_make_edit("remove_hangul_zwsp", removed_run, ""))
    return output, edits


def _compose_modern_jamo(
    units: list[_Unit],
) -> tuple[list[_Unit], list[NormalizationEdit]]:
    """현대 조합형 자모(U+1100 계열)의 명확한 초·중·종 연속열을 조합한다."""
    output: list[_Unit] = []
    edits: list[NormalizationEdit] = []
    changed_run: list[_Unit] = []
    replacement_run: list[str] = []
    index = 0
    while index < len(units):
        choseong = ord(units[index].char)
        if (
            0x1100 <= choseong <= 0x1112
            and index + 1 < len(units)
            and 0x1161 <= ord(units[index + 1].char) <= 0x1175
        ):
            jungseong = ord(units[index + 1].char)
            jongseong_index = 0
            consumed = 2
            if (
                index + 2 < len(units)
                and 0x11A8 <= ord(units[index + 2].char) <= 0x11C2
            ):
                jongseong_index = ord(units[index + 2].char) - 0x11A7
                consumed = 3
            syllable = chr(
                HANGUL_BASE
                + (choseong - 0x1100) * 21 * 28
                + (jungseong - 0x1161) * 28
                + jongseong_index
            )
            source_units = units[index : index + consumed]
            output.append(
                _Unit(
                    syllable,
                    source_units[0].source_start,
                    source_units[-1].source_end,
                )
            )
            changed_run.extend(source_units)
            replacement_run.append(syllable)
            index += consumed
            continue
        if changed_run:
            edits.append(
                _make_edit(
                    "compose_modern_jamo",
                    changed_run,
                    "".join(replacement_run),
                )
            )
            changed_run = []
            replacement_run = []
        output.append(units[index])
        index += 1

    if changed_run:
        edits.append(
            _make_edit(
                "compose_modern_jamo",
                changed_run,
                "".join(replacement_run),
            )
        )
    return output, edits


def _compose_compat_jamo(
    units: list[_Unit],
) -> tuple[list[_Unit], list[NormalizationEdit]]:
    """호환 자모의 명확한 C+V(+C) 연속열을 완성형 음절로 조합한다."""
    output: list[_Unit] = []
    edits: list[NormalizationEdit] = []
    changed_run: list[_Unit] = []
    replacement_run: list[str] = []
    index = 0
    while index < len(units):
        choseong_index = _COMPAT_CHO_INDEX.get(units[index].char)
        if (
            choseong_index is not None
            and index + 1 < len(units)
            and units[index + 1].char in _COMPAT_JUNG_INDEX
        ):
            jungseong_index = _COMPAT_JUNG_INDEX[units[index + 1].char]
            jongseong_index = 0
            consumed = 2
            candidate_index = index + 2
            if candidate_index < len(units):
                candidate = units[candidate_index].char
                candidate_jong = _COMPAT_JONG_INDEX.get(candidate)
                followed_by_vowel = (
                    candidate in _COMPAT_CHO_INDEX
                    and candidate_index + 1 < len(units)
                    and units[candidate_index + 1].char in _COMPAT_JUNG_INDEX
                )
                if candidate_jong is not None and not followed_by_vowel:
                    jongseong_index = candidate_jong
                    consumed = 3
            syllable = chr(
                HANGUL_BASE
                + choseong_index * 21 * 28
                + jungseong_index * 28
                + jongseong_index
            )
            source_units = units[index : index + consumed]
            output.append(
                _Unit(
                    syllable,
                    source_units[0].source_start,
                    source_units[-1].source_end,
                )
            )
            changed_run.extend(source_units)
            replacement_run.append(syllable)
            index += consumed
            continue
        if changed_run:
            edits.append(
                _make_edit(
                    "compose_compat_jamo",
                    changed_run,
                    "".join(replacement_run),
                )
            )
            changed_run = []
            replacement_run = []
        output.append(units[index])
        index += 1

    if changed_run:
        edits.append(
            _make_edit(
                "compose_compat_jamo",
                changed_run,
                "".join(replacement_run),
            )
        )
    return output, edits


def normalize_korean(text: str) -> NormalizationResult:
    """안전하게 확정할 수 있는 한국어 표기 변형만 정규화한다."""
    if not isinstance(text, str):
        raise TypeError("text는 str이어야 합니다.")

    units = [_Unit(char, index, index + 1) for index, char in enumerate(text)]
    edits: list[NormalizationEdit] = []
    rules = (_remove_hangul_zwsp, _compose_modern_jamo, _compose_compat_jamo)
    for transform in rules:
        units, rule_edits = transform(units)
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
