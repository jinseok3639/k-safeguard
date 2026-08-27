"""과거 초성 다중 view 실험을 재현하기 위한 내부 provider."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from ..chosung import ChosungLexicon, generate_chosung_candidates
from ..gateway import CandidateProposal


class ChosungLexiconProvider:
    name = "chosung_lexicon"

    def __init__(
        self,
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
    ) -> None:
        self._lexicon = lexicon
        self._min_initials = min_initials
        self._max_options_per_span = max_options_per_span
        self._max_candidates = max_candidates
        self._allow_segmentation = allow_segmentation
        self._max_segments = max_segments
        self._max_options_per_segment = max_options_per_segment
        self._allow_partial_restoration = allow_partial_restoration
        if isinstance(partial_sources, str):
            raise TypeError("partial_sources는 문자열 이름의 iterable이어야 합니다.")
        self._partial_sources = tuple(partial_sources)
        self._min_partial_initials = min_partial_initials
        self._max_partial_replacements = max_partial_replacements

    def generate(self, text: str) -> Iterator[CandidateProposal]:
        result = generate_chosung_candidates(
            text,
            self._lexicon,
            min_initials=self._min_initials,
            max_options_per_span=self._max_options_per_span,
            max_candidates=self._max_candidates,
            allow_segmentation=self._allow_segmentation,
            max_segments=self._max_segments,
            max_options_per_segment=self._max_options_per_segment,
            allow_partial_restoration=self._allow_partial_restoration,
            partial_sources=self._partial_sources,
            min_partial_initials=self._min_partial_initials,
            max_partial_replacements=self._max_partial_replacements,
        )
        for candidate in result.candidates[1:]:
            lexicon_sources = tuple(
                dict.fromkeys(
                    replacement.lexicon_source for replacement in candidate.replacements
                )
            )
            partial_replacements = tuple(
                replacement
                for replacement in candidate.replacements
                if replacement.partial
            )
            yield CandidateProposal(
                text=candidate.text,
                lossy=True,
                confidence=None,
                metadata=(
                    ("covered_initials", str(candidate.covered_initials)),
                    ("rank_score", str(candidate.rank_score)),
                    ("lexicon_sources", ",".join(lexicon_sources)),
                    (
                        "max_segment_count",
                        str(
                            max(
                                len(replacement.segment_words)
                                for replacement in candidate.replacements
                            )
                        ),
                    ),
                    ("partial_replacement_count", str(len(partial_replacements))),
                    (
                        "partial_ranges",
                        ",".join(
                            f"{replacement.source_start}:{replacement.source_end}"
                            for replacement in partial_replacements
                        ),
                    ),
                    ("generator_version", result.version),
                ),
            )


__all__: list[str] = []
