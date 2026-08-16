"""모델별 출력 계약을 공통 결과로 변환하는 adapter."""

from .kanana_prompt import (
    AdapterResult,
    KananaPromptAdapter,
    parse_kanana_prompt_output,
    to_classifier_result,
)
from .qwen3guard_gen import Qwen3GuardGenAdapter, parse_qwen3guard_output
from .wolf_defender import WolfDefenderAdapter, parse_wolf_defender_label

__all__ = [
    "AdapterResult",
    "KananaPromptAdapter",
    "parse_kanana_prompt_output",
    "to_classifier_result",
    "Qwen3GuardGenAdapter",
    "parse_qwen3guard_output",
    "WolfDefenderAdapter",
    "parse_wolf_defender_label",
]
