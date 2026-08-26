"""과거 wordfreq 초성 다중 view 실험을 재현하기 위한 내부 provider."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..chosung import ChosungLexicon, expand_korean_noun_particles
from .chosung import ChosungLexiconProvider


class WordfreqChosungProvider(ChosungLexiconProvider):
    name = "wordfreq_chosung"

    def __init__(
        self,
        *,
        word_limit: int = 30_000,
        priority_words: Iterable[str] = (),
        priority_source: str = "user",
        expand_priority_particles: bool = False,
        **kwargs: Any,
    ) -> None:
        if word_limit < 1:
            raise ValueError("word_limit은 1 이상이어야 합니다.")
        try:
            from wordfreq import top_n_list
        except ImportError as exc:
            raise ImportError(
                "WordfreqChosungProvider에는 'k-safeguard[wordfreq]' 설치가 필요합니다."
            ) from exc
        raw_priority_words = tuple(priority_words)
        priority_words = raw_priority_words
        if expand_priority_particles:
            priority_words = expand_korean_noun_particles(priority_words)
        sources: list[tuple[str, Iterable[str]]] = []
        if priority_words:
            sources.append((priority_source, priority_words))
        sources.append(("wordfreq:ko", top_n_list("ko", word_limit)))
        lexicon = ChosungLexicon.from_sources(sources)
        if kwargs.get("allow_partial_restoration") and "partial_sources" not in kwargs:
            if not priority_words:
                raise ValueError(
                    "partial restoration에는 priority_words가 하나 이상 필요합니다."
                )
            kwargs["partial_sources"] = (priority_source,)
        super().__init__(lexicon, **kwargs)
        self.word_limit = word_limit
        self.requested_priority_word_count = len(raw_priority_words)
        self.priority_word_count = len(priority_words)


__all__: list[str] = []
