"""선택형 k-safeguard candidate providers."""

from .chosung import ChosungLexiconProvider
from .spaced_jamo import SPACED_JAMO_CANDIDATE_VERSION, SpacedJamoProvider
from .tensify import TENSIFY_CANDIDATE_VERSION, TensifyInverseProvider

__all__ = [
    "SPACED_JAMO_CANDIDATE_VERSION",
    "TENSIFY_CANDIDATE_VERSION",
    "ChosungLexiconProvider",
    "SpacedJamoProvider",
    "TensifyInverseProvider",
]
