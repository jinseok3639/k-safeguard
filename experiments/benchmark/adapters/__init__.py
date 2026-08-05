"""모델별 출력 계약을 공통 결과로 변환하는 adapter."""

from .kanana_prompt import AdapterResult, KananaPromptAdapter, parse_kanana_prompt_output

__all__ = ["AdapterResult", "KananaPromptAdapter", "parse_kanana_prompt_output"]
