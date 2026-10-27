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
    AsyncBatchGuardrailClassifier,
    AsyncGuardrailClassifier,
    BatchClassifierOutput,
    BatchClassifierOutputError,
    BatchGuardrailClassifier,
    ClassifierCallTrace,
    ClassifierErrorMode,
    ClassifierExecutionError,
    ClassifierOutput,
    ClassifierResult,
    GatewayEvaluation,
    GuardrailClassifier,
    ViewEvaluation,
    evaluate_gateway,
    evaluate_gateway_async,
    evaluate_gateway_batch,
    evaluate_gateway_batch_async,
)
from .normalization import (
    NORMALIZER_VERSION,
    NormalizationEdit,
    NormalizationResult,
    normalize_korean,
)


__version__ = "0.2.0"

__all__ = [
    "DEFAULT_MAX_VIEWS",
    "NORMALIZER_VERSION",
    "CandidateProposal",
    "CandidateProvider",
    "AsyncBatchGuardrailClassifier",
    "AsyncGuardrailClassifier",
    "BatchClassifierOutput",
    "BatchClassifierOutputError",
    "BatchGuardrailClassifier",
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
    "GuardrailClassifier",
    "ViewEvaluation",
    "__version__",
    "evaluate_gateway",
    "evaluate_gateway_async",
    "evaluate_gateway_batch",
    "evaluate_gateway_batch_async",
    "normalize_korean",
]
