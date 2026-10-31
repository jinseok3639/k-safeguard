"""k-safeguard public API."""

from .gateway import (
    DEFAULT_MAX_VIEWS,
    CandidateProposal,
    CandidateProvider,
    Gateway,
    GatewayResult,
    TextView,
)
from .execution import (
    AsyncBatchTextClassifier,
    AsyncTextClassifier,
    BatchClassifierOutput,
    BatchClassifierOutputError,
    BatchTextClassifier,
    ClassifierCallTrace,
    ClassifierErrorMode,
    ClassifierExecutionError,
    ClassifierOutput,
    ClassifierResult,
    GatewayEvaluation,
    TextClassifier,
    ViewEvaluation,
)
from .normalization import (
    NORMALIZER_VERSION,
    NormalizationEdit,
    NormalizationResult,
    normalize_korean,
)


__version__ = "1.0.0"

__all__ = [
    "DEFAULT_MAX_VIEWS",
    "NORMALIZER_VERSION",
    "CandidateProposal",
    "CandidateProvider",
    "AsyncBatchTextClassifier",
    "AsyncTextClassifier",
    "BatchClassifierOutput",
    "BatchClassifierOutputError",
    "BatchTextClassifier",
    "ClassifierCallTrace",
    "ClassifierErrorMode",
    "ClassifierExecutionError",
    "ClassifierOutput",
    "ClassifierResult",
    "Gateway",
    "GatewayEvaluation",
    "GatewayResult",
    "NormalizationEdit",
    "NormalizationResult",
    "TextView",
    "TextClassifier",
    "ViewEvaluation",
    "__version__",
    "normalize_korean",
]
