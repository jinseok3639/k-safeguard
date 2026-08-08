"""호출자가 제공한 lexicon을 사용하는 dependency-free 초성 provider."""

from __future__ import annotations

from collections.abc import Iterator

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
    ) -> None:
        self._lexicon = lexicon
        self._min_initials = min_initials
        self._max_options_per_span = max_options_per_span
        self._max_candidates = max_candidates

    def generate(self, text: str) -> Iterator[CandidateProposal]:
        result = generate_chosung_candidates(
            text,
            self._lexicon,
            min_initials=self._min_initials,
            max_options_per_span=self._max_options_per_span,
            max_candidates=self._max_candidates,
        )
        for candidate in result.candidates[1:]:
            lexicon_sources = tuple(
                dict.fromkeys(
                    replacement.lexicon_source for replacement in candidate.replacements
                )
            )
            yield CandidateProposal(
                text=candidate.text,
                lossy=True,
                confidence=None,
                metadata=(
                    ("covered_initials", str(candidate.covered_initials)),
                    ("rank_score", str(candidate.rank_score)),
                    ("lexicon_sources", ",".join(lexicon_sources)),
                    ("generator_version", result.version),
                ),
            )


__all__ = ["ChosungLexiconProvider"]
