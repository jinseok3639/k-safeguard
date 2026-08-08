"""k-safeguard public API."""

from .chosung import (
    CHOSUNG_CANDIDATE_VERSION,
    ChosungCandidate,
    ChosungCandidateResult,
    ChosungLexicon,
    ChosungReplacement,
    LexiconPartialMatch,
    chosung_signature,
    expand_korean_noun_particles,
    generate_chosung_candidates,
)
from .gateway import (
    CandidateProposal,
    CandidateProvider,
    Gateway,
    GatewayResult,
    TextView,
)
from .normalization import (
    NORMALIZER_VERSION,
    NormalizationEdit,
    NormalizationResult,
    normalize_korean,
)


__version__ = "0.1.0"

__all__ = [
    "CHOSUNG_CANDIDATE_VERSION",
    "NORMALIZER_VERSION",
    "CandidateProposal",
    "CandidateProvider",
    "ChosungCandidate",
    "ChosungCandidateResult",
    "ChosungLexicon",
    "ChosungReplacement",
    "Gateway",
    "GatewayResult",
    "LexiconPartialMatch",
    "NormalizationEdit",
    "NormalizationResult",
    "TextView",
    "__version__",
    "chosung_signature",
    "expand_korean_noun_particles",
    "generate_chosung_candidates",
    "normalize_korean",
]
