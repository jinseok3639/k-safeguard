"""k-safeguard의 opt-in 초성체 다중 후보 생성기.

초성체는 정보가 소실된 many-to-one 변환이므로 단일 문자열로 정규화하지 않는다.
호출자가 제공한 일반 어휘 사전에서 제한된 후보를 만들고 원문 view를 항상 함께 반환한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


CHOSUNG_CANDIDATE_VERSION = "0.4.0"
HANGUL_BASE = 0xAC00
COMPAT_CHO = (
    "ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ",
    "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ",
)
_COMPAT_CHO_SET = frozenset(COMPAT_CHO)
_MAX_SEGMENTS = 4
_MAX_OPTIONS_PER_SEGMENT = 4


def _is_hangul_syllable(char: str) -> bool:
    return 0xAC00 <= ord(char) <= 0xD7A3


def _initial(char: str) -> str:
    return COMPAT_CHO[(ord(char) - HANGUL_BASE) // 588]


def chosung_signature(word: str) -> str | None:
    """완성형 한글 단어의 초성 서명을 반환한다."""
    if not word or not all(_is_hangul_syllable(char) for char in word):
        return None
    return "".join(_initial(char) for char in word)


def expand_korean_noun_particles(words: Iterable[str]) -> tuple[str, ...]:
    """완성형 한글 명사에 자주 쓰이는 조사를 결정론적으로 확장한다.

    사용자·도메인 사전용 opt-in helper이며 일반 빈도 사전에는 자동 적용하지 않는다.
    """

    expanded: list[str] = []
    seen: set[str] = set()
    for raw_word in words:
        if not isinstance(raw_word, str):
            raise TypeError("lexicon 단어는 str이어야 합니다.")
        word = raw_word.strip()
        signature = chosung_signature(word)
        if signature is None:
            variants = (word,)
        else:
            jongseong = (ord(word[-1]) - HANGUL_BASE) % 28
            has_final = jongseong != 0
            variants = (
                word,
                word + ("은" if has_final else "는"),
                word + ("이" if has_final else "가"),
                word + ("을" if has_final else "를"),
                word + ("과" if has_final else "와"),
                word + ("으로" if has_final and jongseong != 8 else "로"),
                word + "의",
                word + "에",
                word + "에서",
                word + "도",
                word + "만",
            )
        for variant in variants:
            if variant not in seen:
                seen.add(variant)
                expanded.append(variant)
    return tuple(expanded)


@dataclass(frozen=True)
class LexiconEntry:
    word: str
    rank: int
    signature: str
    source: str = "default"
    source_rank: int = 0


@dataclass(frozen=True)
class LexiconSegmentation:
    entries: tuple[LexiconEntry, ...]

    @property
    def word(self) -> str:
        return "".join(entry.word for entry in self.entries)

    @property
    def rank_score(self) -> int:
        return sum(entry.rank for entry in self.entries)


@dataclass(frozen=True)
class LexiconPartialMatch:
    start: int
    end: int
    entry: LexiconEntry


class ChosungLexicon:
    """빈도순 단어 iterable을 초성 패턴 검색용으로 인덱싱한다."""

    def __init__(
        self,
        words: Iterable[str],
        *,
        min_word_length: int = 2,
        max_word_length: int = 12,
    ) -> None:
        self._build(
            (("default", words),),
            min_word_length=min_word_length,
            max_word_length=max_word_length,
        )

    @classmethod
    def from_sources(
        cls,
        sources: Iterable[tuple[str, Iterable[str]]],
        *,
        min_word_length: int = 2,
        max_word_length: int = 12,
    ) -> ChosungLexicon:
        """앞에 둔 source를 우선해 여러 어휘 iterable을 하나로 병합한다.

        동일 단어가 여러 source에 있으면 가장 먼저 선언한 source만 보존한다.
        """

        instance = cls.__new__(cls)
        instance._build(
            sources,
            min_word_length=min_word_length,
            max_word_length=max_word_length,
        )
        return instance

    def _build(
        self,
        sources: Iterable[tuple[str, Iterable[str]]],
        *,
        min_word_length: int,
        max_word_length: int,
    ) -> None:
        if min_word_length < 1 or max_word_length < min_word_length:
            raise ValueError("단어 길이 범위가 잘못됐습니다.")

        by_length: dict[int, list[LexiconEntry]] = {}
        by_signature: dict[str, list[LexiconEntry]] = {}
        source_counts: dict[str, int] = {}
        seen: set[str] = set()
        global_rank = 0
        for source, words in sources:
            if not isinstance(source, str) or not source.strip():
                raise ValueError("lexicon source 이름은 비어 있지 않은 str이어야 합니다.")
            source = source.strip()
            if source in source_counts:
                raise ValueError(f"중복 lexicon source: {source}")
            source_counts[source] = 0
            for source_rank, raw_word in enumerate(words):
                if not isinstance(raw_word, str):
                    raise TypeError("lexicon 단어는 str이어야 합니다.")
                word = raw_word.strip()
                rank = global_rank
                global_rank += 1
                if word in seen or not min_word_length <= len(word) <= max_word_length:
                    continue
                signature = chosung_signature(word)
                if signature is None:
                    continue
                seen.add(word)
                source_counts[source] += 1
                entry = LexiconEntry(
                    word=word,
                    rank=rank,
                    signature=signature,
                    source=source,
                    source_rank=source_rank,
                )
                by_length.setdefault(len(word), []).append(entry)
                by_signature.setdefault(signature, []).append(entry)

        self._by_length = {length: tuple(entries) for length, entries in by_length.items()}
        self._by_signature = {
            signature: tuple(entries) for signature, entries in by_signature.items()
        }
        self.word_count = len(seen)
        self.source_counts = tuple(source_counts.items())
        self._min_word_length = min_word_length
        self._max_word_length = max_word_length

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

    def match_segmented(
        self,
        pattern: str,
        limit: int,
        *,
        max_segments: int = 2,
        max_options_per_segment: int = 1,
    ) -> tuple[LexiconSegmentation, ...]:
        """완전 초성 pattern을 둘 이상의 사전 단위로 분할해 일치시킨다."""

        if limit < 1:
            raise ValueError("limit은 1 이상이어야 합니다.")
        if not 2 <= max_segments <= _MAX_SEGMENTS:
            raise ValueError(f"max_segments는 2~{_MAX_SEGMENTS}여야 합니다.")
        if not 1 <= max_options_per_segment <= _MAX_OPTIONS_PER_SEGMENT:
            raise ValueError(
                f"max_options_per_segment는 1~{_MAX_OPTIONS_PER_SEGMENT}여야 합니다."
            )
        if not pattern or not all(char in _COMPAT_CHO_SET for char in pattern):
            return ()

        completed: list[LexiconSegmentation] = []

        def search(offset: int, entries: tuple[LexiconEntry, ...]) -> None:
            if offset == len(pattern):
                if len(entries) >= 2:
                    completed.append(LexiconSegmentation(entries))
                return
            if len(entries) == max_segments:
                return

            min_end = offset + self._min_word_length
            max_end = min(len(pattern), offset + self._max_word_length)
            for end in range(max_end, min_end - 1, -1):
                remaining = len(pattern) - end
                if remaining and remaining < self._min_word_length:
                    continue
                options = self._by_signature.get(pattern[offset:end], ())
                for option in options[:max_options_per_segment]:
                    search(end, entries + (option,))

        search(0, ())
        deduplicated: dict[str, LexiconSegmentation] = {}
        for segmentation in completed:
            previous = deduplicated.get(segmentation.word)
            key = (segmentation.rank_score, len(segmentation.entries), segmentation.word)
            if previous is None or key < (
                previous.rank_score,
                len(previous.entries),
                previous.word,
            ):
                deduplicated[segmentation.word] = segmentation
        ranked = sorted(
            deduplicated.values(),
            key=lambda item: (item.rank_score, len(item.entries), item.word),
        )
        return tuple(ranked[:limit])

    def match_partial(
        self,
        pattern: str,
        limit: int,
        *,
        sources: Iterable[str],
        min_initials: int = 3,
    ) -> tuple[LexiconPartialMatch, ...]:
        """완전 초성 pattern 내부의 신뢰 source 단어를 제한적으로 찾는다."""

        if limit < 1:
            raise ValueError("limit은 1 이상이어야 합니다.")
        if min_initials < 1:
            raise ValueError("min_initials는 1 이상이어야 합니다.")
        if not pattern or not all(char in _COMPAT_CHO_SET for char in pattern):
            return ()

        if isinstance(sources, str):
            raise TypeError("partial restoration sources는 문자열 iterable이어야 합니다.")
        source_set = frozenset(sources)
        if not source_set or any(
            not isinstance(source, str) or not source.strip() for source in source_set
        ):
            raise ValueError("partial restoration source를 하나 이상 지정해야 합니다.")

        matches: list[LexiconPartialMatch] = []
        max_length = min(self._max_word_length, len(pattern) - 1)
        for length in range(max_length, min_initials - 1, -1):
            for start in range(0, len(pattern) - length + 1):
                end = start + length
                for entry in self._by_signature.get(pattern[start:end], ()):
                    if entry.source in source_set:
                        matches.append(LexiconPartialMatch(start, end, entry))

        ranked = sorted(
            matches,
            key=lambda item: (
                -(item.end - item.start),
                item.entry.rank,
                item.start,
                item.entry.word,
            ),
        )
        return tuple(ranked[:limit])


@dataclass(frozen=True)
class ChosungReplacement:
    source_start: int
    source_end: int
    before: str
    after: str
    lexicon_rank: int
    alternatives: int
    lexicon_source: str = "default"
    source_rank: int = 0
    segment_words: tuple[str, ...] = ()
    segment_sources: tuple[str, ...] = ()
    partial: bool = False


@dataclass(frozen=True)
class _LexiconOption:
    span_text: str
    replacement_text: str
    relative_start: int
    relative_end: int
    covered_initials: int
    partial: bool
    rank_score: int
    source_rank: int
    segment_words: tuple[str, ...]
    segment_sources: tuple[str, ...]

    @property
    def source(self) -> str:
        return "+".join(dict.fromkeys(self.segment_sources))


def _lexicon_options(
    pattern: str,
    lexicon: ChosungLexicon,
    *,
    limit: int,
    allow_segmentation: bool,
    max_segments: int,
    max_options_per_segment: int,
    allow_partial_restoration: bool,
    partial_sources: tuple[str, ...],
    min_partial_initials: int,
) -> tuple[tuple[_LexiconOption, ...], bool]:
    direct = lexicon.match(pattern, limit + 1)
    options = [
        _LexiconOption(
            entry.word,
            entry.word,
            0,
            len(pattern),
            sum(char in _COMPAT_CHO_SET for char in pattern),
            False,
            entry.rank,
            entry.source_rank,
            (entry.word,),
            (entry.source,),
        )
        for entry in direct
    ]
    if allow_segmentation:
        segmented = lexicon.match_segmented(
            pattern,
            limit + 1,
            max_segments=max_segments,
            max_options_per_segment=max_options_per_segment,
        )
        options.extend(
            _LexiconOption(
                item.word,
                item.word,
                0,
                len(pattern),
                len(pattern),
                False,
                item.rank_score,
                sum(entry.source_rank for entry in item.entries),
                tuple(entry.word for entry in item.entries),
                tuple(entry.source for entry in item.entries),
            )
            for item in segmented
        )

    if allow_partial_restoration:
        partial_matches = lexicon.match_partial(
            pattern,
            limit + 1,
            sources=partial_sources,
            min_initials=min_partial_initials,
        )
        options.extend(
            _LexiconOption(
                pattern[: item.start] + item.entry.word + pattern[item.end :],
                item.entry.word,
                item.start,
                item.end,
                item.end - item.start,
                True,
                item.entry.rank,
                item.entry.source_rank,
                (item.entry.word,),
                (item.entry.source,),
            )
            for item in partial_matches
        )

    deduplicated: dict[str, _LexiconOption] = {}
    for option in options:
        previous = deduplicated.get(option.span_text)
        key = (
            -option.covered_initials,
            option.rank_score,
            len(option.segment_words),
            option.span_text,
        )
        if previous is None or key < (
            -previous.covered_initials,
            previous.rank_score,
            len(previous.segment_words),
            previous.span_text,
        ):
            deduplicated[option.span_text] = option
    ranked = sorted(
        deduplicated.values(),
        key=lambda item: (
            -item.covered_initials,
            item.rank_score,
            len(item.segment_words),
            item.span_text,
        ),
    )
    return tuple(ranked[:limit]), len(ranked) > limit


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
    allow_segmentation: bool = False,
    max_segments: int = 2,
    max_options_per_segment: int = 1,
    allow_partial_restoration: bool = False,
    partial_sources: Iterable[str] = (),
    min_partial_initials: int = 3,
    max_partial_replacements: int = 1,
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
    if not 2 <= max_segments <= _MAX_SEGMENTS:
        raise ValueError(f"max_segments는 2~{_MAX_SEGMENTS}여야 합니다.")
    if not 1 <= max_options_per_segment <= _MAX_OPTIONS_PER_SEGMENT:
        raise ValueError(
            f"max_options_per_segment는 1~{_MAX_OPTIONS_PER_SEGMENT}여야 합니다."
        )
    if min_partial_initials < 1:
        raise ValueError("min_partial_initials는 1 이상이어야 합니다.")
    if max_partial_replacements < 1:
        raise ValueError("max_partial_replacements는 1 이상이어야 합니다.")
    if isinstance(partial_sources, str):
        raise TypeError("partial_sources는 문자열 iterable이어야 합니다.")
    partial_source_names = tuple(dict.fromkeys(partial_sources))
    if allow_partial_restoration and not partial_source_names:
        raise ValueError("partial restoration source를 하나 이상 지정해야 합니다.")

    original_candidate = ChosungCandidate(text, (), 0, 0, False)
    states = [original_candidate]
    matched_spans = 0
    truncated = False

    for start, end in _chosung_spans(text):
        pattern = text[start:end]
        initial_count = sum(char in _COMPAT_CHO_SET for char in pattern)
        if initial_count < min_initials or _is_repeated_chat_initials(pattern):
            continue
        options, options_truncated = _lexicon_options(
            pattern,
            lexicon,
            limit=max_options_per_span,
            allow_segmentation=allow_segmentation,
            max_segments=max_segments,
            max_options_per_segment=max_options_per_segment,
            allow_partial_restoration=allow_partial_restoration,
            partial_sources=partial_source_names,
            min_partial_initials=min_partial_initials,
        )
        if not options:
            continue
        if options_truncated:
            truncated = True
        matched_spans += 1
        alternatives = len(options)
        expanded = list(states)
        for state in states:
            for option in options:
                if option.partial and sum(
                    replacement.partial for replacement in state.replacements
                ) >= max_partial_replacements:
                    continue
                replacement_start = start + option.relative_start
                replacement_end = start + option.relative_end
                replacement = ChosungReplacement(
                    replacement_start,
                    replacement_end,
                    text[replacement_start:replacement_end],
                    option.replacement_text,
                    option.rank_score,
                    alternatives,
                    option.source,
                    option.source_rank,
                    option.segment_words,
                    option.segment_sources,
                    option.partial,
                )
                expanded.append(
                    ChosungCandidate(
                        state.text[:start] + option.span_text + state.text[end:],
                        state.replacements + (replacement,),
                        state.covered_initials + option.covered_initials,
                        state.rank_score + option.rank_score,
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
    "LexiconPartialMatch",
    "LexiconSegmentation",
    "chosung_signature",
    "expand_korean_noun_particles",
    "generate_chosung_candidates",
]
