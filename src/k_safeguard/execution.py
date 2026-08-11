"""Gateway view를 외부 가드레일 classifier로 판정하는 무의존 실행 레이어."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Literal, TypeAlias

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
AsyncGuardrailClassifier: TypeAlias = Callable[[str], Awaitable[ClassifierOutput]]


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


def _validate_execution_options(
    classifier: object,
    error_mode: ClassifierErrorMode,
    stop_on_block: bool,
) -> None:
    if error_mode not in {"raise", "block", "allow"}:
        raise ValueError("error_mode는 raise, block, allow 중 하나여야 합니다.")
    if not callable(classifier):
        raise TypeError("classifier는 호출 가능해야 합니다.")
    if not isinstance(stop_on_block, bool):
        raise TypeError("stop_on_block은 bool이어야 합니다.")


@dataclass
class _EvaluationAccumulator:
    """동기·비동기 실행 경로가 공유하는 판정 정책 상태."""

    gateway_result: GatewayResult
    error_mode: ClassifierErrorMode
    stop_on_block: bool
    evaluations: list[ViewEvaluation] = field(default_factory=list)
    classifier_errors: list[str] = field(default_factory=list)
    blocked: bool = False
    category: str | None = None
    decision_source: Literal["classifier", "error_policy", "no_block"] = "no_block"
    trigger_view_index: int | None = None

    def record(
        self,
        index: int,
        view: TextView,
        result: ClassifierResult,
        latency_ms: float,
        cause: Exception | None,
    ) -> bool:
        """하나의 판정을 기록하고 남은 view 평가 중단 여부를 반환한다."""
        self.evaluations.append(ViewEvaluation(index, view, result, latency_ms))

        if result.error is not None:
            error_type = result.error
            self.classifier_errors.append(f"view[{index}]:{error_type}")
            if self.error_mode == "raise":
                error = ClassifierExecutionError(index, error_type)
                if cause is not None:
                    raise error from cause
                raise error
            if self.error_mode == "block":
                if not self.blocked:
                    self.blocked = True
                    self.decision_source = "error_policy"
                    self.trigger_view_index = index
                return self.stop_on_block
            return False

        if result.block:
            if not self.blocked:
                self.category = result.category
                self.decision_source = "classifier"
                self.trigger_view_index = index
            self.blocked = True
            return self.stop_on_block
        return False

    def finish(self) -> GatewayEvaluation:
        return GatewayEvaluation(
            gateway=self.gateway_result,
            block=self.blocked,
            category=self.category,
            evaluations=tuple(self.evaluations),
            classifier_errors=tuple(self.classifier_errors),
            decision_source=self.decision_source,
            trigger_view_index=self.trigger_view_index,
            stopped_early=len(self.evaluations) < len(self.gateway_result.views),
        )


def evaluate_gateway(
    gateway_result: GatewayResult,
    classifier: GuardrailClassifier,
    *,
    error_mode: ClassifierErrorMode = "raise",
    stop_on_block: bool = True,
) -> GatewayEvaluation:
    """정렬된 Gateway view를 판정하고 OR 정책으로 최종 block을 계산한다."""
    _validate_execution_options(classifier, error_mode, stop_on_block)
    accumulator = _EvaluationAccumulator(gateway_result, error_mode, stop_on_block)

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
        if accumulator.record(index, view, result, latency_ms, cause):
            break

    return accumulator.finish()


async def evaluate_gateway_async(
    gateway_result: GatewayResult,
    classifier: AsyncGuardrailClassifier,
    *,
    error_mode: ClassifierErrorMode = "raise",
    stop_on_block: bool = True,
) -> GatewayEvaluation:
    """async classifier로 view를 순차 판정하고 동기 API와 같은 정책을 적용한다."""
    _validate_execution_options(classifier, error_mode, stop_on_block)
    accumulator = _EvaluationAccumulator(gateway_result, error_mode, stop_on_block)

    for index, view in enumerate(gateway_result.views):
        started = time.perf_counter()
        cause: Exception | None = None
        try:
            result = _normalize_output(await classifier(view.text))
        except Exception as exc:
            cause = exc
            result = ClassifierResult(
                block=None,
                error=f"{type(exc).__name__}",
            )
        latency_ms = (time.perf_counter() - started) * 1000
        if accumulator.record(index, view, result, latency_ms, cause):
            break

    return accumulator.finish()


__all__ = [
    "AsyncGuardrailClassifier",
    "ClassifierErrorMode",
    "ClassifierExecutionError",
    "ClassifierOutput",
    "ClassifierResult",
    "GatewayEvaluation",
    "GuardrailClassifier",
    "ViewEvaluation",
    "evaluate_gateway",
    "evaluate_gateway_async",
]
