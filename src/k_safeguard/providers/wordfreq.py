"""`k-safeguard[wordfreq]`에서만 사용할 수 있는 실험적 provider."""

from __future__ import annotations

from typing import Any

from ..chosung import ChosungLexicon
from .chosung import ChosungLexiconProvider


class WordfreqChosungProvider(ChosungLexiconProvider):
    name = "wordfreq_chosung"

    def __init__(self, *, word_limit: int = 30_000, **kwargs: Any) -> None:
        if word_limit < 1:
            raise ValueError("word_limit은 1 이상이어야 합니다.")
        try:
            from wordfreq import top_n_list
        except ImportError as exc:
            raise ImportError(
                "WordfreqChosungProvider에는 'k-safeguard[wordfreq]' 설치가 필요합니다."
            ) from exc
        super().__init__(ChosungLexicon(top_n_list("ko", word_limit)), **kwargs)
        self.word_limit = word_limit


__all__ = ["WordfreqChosungProvider"]
