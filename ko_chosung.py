"""초성체 입력을 위한 보수적인 다중 후보 생성기.

초성체는 정보가 소실된 many-to-one 변환이므로 단일 문자열로 정규화하지 않는다.
호출자가 제공한 일반 어휘 사전에서 제한된 후보를 만들고 원문 view를 항상 함께 반환한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


CHOSUNG_CANDIDATE_VERSION = "0.1.0"
HANGUL_BASE = 0xAC00
COMPAT_CHO = (
    "ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ",
    "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ",
)
_COMPAT_CHO_SET = frozenset(COMPAT_CHO)


def _is_hangul_syllable(char: str) -> bool:
    return 0xAC00 <= ord(char) <= 0xD7A3


def _initial(char: str) -> str:
    return COMPAT_CHO[(ord(char) - HANGUL_BASE) // 588]


def chosung_signature(word: str) -> str | None:
    """완성형 한글 단어의 초성 서명을 반환한다."""
    if not word or not all(_is_hangul_syllable(char) for char in word):
        return None
    return "".join(_initial(char) for char in word)


@dataclass(frozen=True)
class LexiconEntry:
    word: str
    rank: int
    signature: str


class ChosungLexicon:
    """빈도순 단어 iterable을 초성 패턴 검색용으로 인덱싱한다."""

    def __init__(
        self,
        words: Iterable[str],
        *,
        min_word_length: int = 2,
        max_word_length: int = 12,
    ) -> None:
        if min_word_length < 1 or max_word_length < min_word_length:
            raise ValueError("단어 길이 범위가 잘못됐습니다.")

        by_length: dict[int, list[LexiconEntry]] = {}
        by_signature: dict[str, list[LexiconEntry]] = {}
        seen: set[str] = set()
        for rank, raw_word in enumerate(words):
            word = raw_word.strip()
            if word in seen or not min_word_length <= len(word) <= max_word_length:
                continue
            signature = chosung_signature(word)
            if signature is None:
                continue
            seen.add(word)
            entry = LexiconEntry(word=word, rank=rank, signature=signature)
            by_length.setdefault(len(word), []).append(entry)
            by_signature.setdefault(signature, []).append(entry)

        self._by_length = {length: tuple(entries) for length, entries in by_length.items()}
        self._by_signature = {
            signature: tuple(entries) for signature, entries in by_signature.items()
        }
        self.word_count = len(seen)

    def match(self, pattern: str, limit: int) -> tuple[LexiconEntry, ...]:
        """한글 음절은 그대로, 호환 초성은 후보 음절의 초성과 대조한다."""
        if limit < 1:
            raise ValueError("limit은 1 이상이어야 합니다.")
        if pattern and all(char in _COMPAT_CHO_SET for char in pattern):
            return self._by_signature.get(pattern, ())[:limit]

        matches: list[LexiconEntry] = []
        for entry in self._by_length.get(len(pattern), ()):
            if all(
                source == candidate
                if _is_hangul_syllable(source)
                else source in _COMPAT_CHO_SET and source == _initial(candidate)
                for source, candidate in zip(pattern, entry.word)
            ):
                matches.append(entry)
                if len(matches) == limit:
                    break
        return tuple(matches)


@dataclass(frozen=True)
class ChosungReplacement:
    source_start: int
    source_end: int
    before: str
    after: str
    lexicon_rank: int
    alternatives: int


@dataclass(frozen=True)
class ChosungCandidate:
    text: str
    replacements: tuple[ChosungReplacement, ...]
    covered_initials: int
    rank_score: int
    lossy: bool


@dataclass(frozen=True)
class ChosungCandidateResult:
    original: str
    candidates: tuple[ChosungCandidate, ...]
    matched_spans: int
    truncated: bool
    lexicon_words: int
    version: str = CHOSUNG_CANDIDATE_VERSION


def _chosung_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for index, char in enumerate(text):
        if _is_hangul_syllable(char) or char in _COMPAT_CHO_SET:
            if start is None:
                start = index
        elif start is not None:
            spans.append((start, index))
            start = None
    if start is not None:
        spans.append((start, len(text)))
    return spans


def _is_repeated_chat_initials(pattern: str) -> bool:
    return (
        len(pattern) >= 2
        and all(char in _COMPAT_CHO_SET for char in pattern)
        and len(set(pattern)) == 1
    )


def generate_chosung_candidates(
    text: str,
    lexicon: ChosungLexicon,
    *,
    min_initials: int = 3,
    max_options_per_span: int = 3,
    max_candidates: int = 16,
) -> ChosungCandidateResult:
    """원문 view와 제한된 초성 복원 후보를 결정론적으로 반환한다.

    후보는 더 많은 초성을 복원한 문장, 사전 빈도 순위 합이 낮은 문장 순으로 정렬한다.
    반복 초성만으로 된 통신체(`ㅋㅋ`, `ㅎㅎㅎ` 등)는 과잉 복원을 피하기 위해 건너뛴다.
    """
    if not isinstance(text, str):
        raise TypeError("text는 str이어야 합니다.")
    if min_initials < 1:
        raise ValueError("min_initials는 1 이상이어야 합니다.")
    if max_options_per_span < 1 or max_candidates < 1:
        raise ValueError("후보 제한은 1 이상이어야 합니다.")

    original_candidate = ChosungCandidate(text, (), 0, 0, False)
    states = [original_candidate]
    matched_spans = 0
    truncated = False

    for start, end in _chosung_spans(text):
        pattern = text[start:end]
        initial_count = sum(char in _COMPAT_CHO_SET for char in pattern)
        if initial_count < min_initials or _is_repeated_chat_initials(pattern):
            continue
        options = lexicon.match(pattern, max_options_per_span + 1)
        if not options:
            continue
        if len(options) > max_options_per_span:
            options = options[:max_options_per_span]
            truncated = True
        matched_spans += 1
        alternatives = len(options)
        expanded = list(states)
        for state in states:
            for option in options:
                replacement = ChosungReplacement(
                    start,
                    end,
                    pattern,
                    option.word,
                    option.rank,
                    alternatives,
                )
                expanded.append(
                    ChosungCandidate(
                        state.text[:start] + option.word + state.text[end:],
                        state.replacements + (replacement,),
                        state.covered_initials + initial_count,
                        state.rank_score + option.rank,
                        True,
                    )
                )

        deduplicated: dict[str, ChosungCandidate] = {}
        for candidate in expanded:
            previous = deduplicated.get(candidate.text)
            rank_key = (-candidate.covered_initials, candidate.rank_score, candidate.text)
            if previous is None or rank_key < (
                -previous.covered_initials,
                previous.rank_score,
                previous.text,
            ):
                deduplicated[candidate.text] = candidate
        ranked = sorted(
            (candidate for candidate in deduplicated.values() if candidate.text != text),
            key=lambda candidate: (
                -candidate.covered_initials,
                candidate.rank_score,
                candidate.text,
            ),
        )
        if len(ranked) + 1 > max_candidates:
            ranked = ranked[: max_candidates - 1]
            truncated = True
        states = [original_candidate, *ranked]

    return ChosungCandidateResult(
        original=text,
        candidates=tuple(states),
        matched_spans=matched_spans,
        truncated=truncated,
        lexicon_words=lexicon.word_count,
    )


__all__ = [
    "CHOSUNG_CANDIDATE_VERSION",
    "ChosungCandidate",
    "ChosungCandidateResult",
    "ChosungLexicon",
    "ChosungReplacement",
    "LexiconEntry",
    "chosung_signature",
    "generate_chosung_candidates",
]
