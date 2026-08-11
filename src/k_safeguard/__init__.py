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
    DEFAULT_MAX_VIEWS,
    CandidateProposal,
    CandidateProvider,
    Gateway,
    GatewayResult,
    TextView,
)
from .execution import (
    ClassifierErrorMode,
    ClassifierExecutionError,
    ClassifierOutput,
    ClassifierResult,
    GatewayEvaluation,
    GuardrailClassifier,
    ViewEvaluation,
    evaluate_gateway,
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
    "DEFAULT_MAX_VIEWS",
    "NORMALIZER_VERSION",
    "CandidateProposal",
    "CandidateProvider",
    "ClassifierErrorMode",
    "ClassifierExecutionError",
    "ClassifierOutput",
    "ClassifierResult",
    "ChosungCandidate",
    "ChosungCandidateResult",
    "ChosungLexicon",
    "ChosungReplacement",
    "Gateway",
    "GatewayEvaluation",
    "GatewayResult",
    "LexiconPartialMatch",
    "NormalizationEdit",
    "NormalizationResult",
    "TextView",
    "GuardrailClassifier",
    "ViewEvaluation",
    "__version__",
    "chosung_signature",
    "expand_korean_noun_particles",
    "evaluate_gateway",
    "generate_chosung_candidates",
    "normalize_korean",
]
