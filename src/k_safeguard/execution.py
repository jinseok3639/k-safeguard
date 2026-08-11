"""Gateway view를 외부 가드레일 classifier로 판정하는 무의존 실행 레이어."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Literal, TypeAlias

from .gateway import GatewayResult, Metadata, TextView


ClassifierErrorMode: TypeAlias = Literal["raise", "block", "allow"]


@dataclass(frozen=True)
class ClassifierResult:
    """외부 classifier의 정규화된 단일 view 판정."""

    block: bool | None
    category: str | None = None
    error: str | None = None
    metadata: Metadata = ()

    def __post_init__(self) -> None:
        if self.block is not None and not isinstance(self.block, bool):
            raise TypeError("classifier block은 bool 또는 None이어야 합니다.")
        if self.block is None and not self.error:
            raise ValueError("block=None이면 classifier error가 필요합니다.")
        if self.block is not None and self.error is not None:
            raise ValueError("classifier 판정과 error를 동시에 반환할 수 없습니다.")
        if self.error is not None and not isinstance(self.error, str):
            raise TypeError("classifier error는 str 또는 None이어야 합니다.")
        if self.category is not None and not isinstance(self.category, str):
            raise TypeError("classifier category는 str 또는 None이어야 합니다.")


ClassifierOutput: TypeAlias = bool | ClassifierResult
GuardrailClassifier: TypeAlias = Callable[[str], ClassifierOutput]


@dataclass(frozen=True)
class ViewEvaluation:
    """한 text view와 classifier 결과의 추적 정보."""

    index: int
    view: TextView
    result: ClassifierResult
    latency_ms: float


@dataclass(frozen=True)
class GatewayEvaluation:
    """Gateway 전처리와 모든 실행된 view 판정을 묶은 최종 결과."""

    gateway: GatewayResult
    block: bool
    category: str | None
    evaluations: tuple[ViewEvaluation, ...]
    classifier_errors: tuple[str, ...]
    decision_source: Literal["classifier", "error_policy", "no_block"]
    trigger_view_index: int | None
    stopped_early: bool

    @property
    def evaluated_view_count(self) -> int:
        return len(self.evaluations)


class ClassifierExecutionError(RuntimeError):
    """classifier 호출이나 반환값 검증 실패를 view 위치와 함께 전달한다."""

    def __init__(self, view_index: int, error_type: str) -> None:
        self.view_index = view_index
        self.error_type = error_type
        super().__init__(
            f"classifier 실행 실패(view_index={view_index}, error_type={error_type})"
        )


def _normalize_output(output: ClassifierOutput) -> ClassifierResult:
    if isinstance(output, bool):
        return ClassifierResult(block=output)
    if isinstance(output, ClassifierResult):
        return output
    raise TypeError("classifier는 bool 또는 ClassifierResult를 반환해야 합니다.")


def evaluate_gateway(
    gateway_result: GatewayResult,
    classifier: GuardrailClassifier,
    *,
    error_mode: ClassifierErrorMode = "raise",
    stop_on_block: bool = True,
) -> GatewayEvaluation:
    """정렬된 Gateway view를 판정하고 OR 정책으로 최종 block을 계산한다."""
    if error_mode not in {"raise", "block", "allow"}:
        raise ValueError("error_mode는 raise, block, allow 중 하나여야 합니다.")
    if not callable(classifier):
        raise TypeError("classifier는 호출 가능해야 합니다.")
    if not isinstance(stop_on_block, bool):
        raise TypeError("stop_on_block은 bool이어야 합니다.")

    evaluations: list[ViewEvaluation] = []
    classifier_errors: list[str] = []
    blocked = False
    category: str | None = None
    decision_source: Literal["classifier", "error_policy", "no_block"] = "no_block"
    trigger_view_index: int | None = None

    for index, view in enumerate(gateway_result.views):
        started = time.perf_counter()
        cause: Exception | None = None
        try:
            result = _normalize_output(classifier(view.text))
        except Exception as exc:
            cause = exc
            result = ClassifierResult(
                block=None,
                error=f"{type(exc).__name__}",
            )
        latency_ms = (time.perf_counter() - started) * 1000
        evaluations.append(ViewEvaluation(index, view, result, latency_ms))

        if result.error is not None:
            error_type = result.error
            classifier_errors.append(f"view[{index}]:{error_type}")
            if error_mode == "raise":
                error = ClassifierExecutionError(index, error_type)
                if cause is not None:
                    raise error from cause
                raise error
            if error_mode == "block":
                if not blocked:
                    blocked = True
                    decision_source = "error_policy"
                    trigger_view_index = index
                if stop_on_block:
                    break
            continue

        if result.block:
            if not blocked:
                category = result.category
                decision_source = "classifier"
                trigger_view_index = index
            blocked = True
            if stop_on_block:
                break

    return GatewayEvaluation(
        gateway=gateway_result,
        block=blocked,
        category=category,
        evaluations=tuple(evaluations),
        classifier_errors=tuple(classifier_errors),
        decision_source=decision_source,
        trigger_view_index=trigger_view_index,
        stopped_early=len(evaluations) < len(gateway_result.views),
    )


__all__ = [
    "ClassifierErrorMode",
    "ClassifierExecutionError",
    "ClassifierOutput",
    "ClassifierResult",
    "GatewayEvaluation",
    "GuardrailClassifier",
    "ViewEvaluation",
    "evaluate_gateway",
]
