"""Gateway view를 외부 가드레일 classifier로 판정하는 무의존 실행 레이어."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Iterable, Literal, TypeAlias

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
BatchClassifierOutput: TypeAlias = Iterable[ClassifierOutput]
BatchGuardrailClassifier: TypeAlias = Callable[[tuple[str, ...]], BatchClassifierOutput]
AsyncBatchGuardrailClassifier: TypeAlias = Callable[
    [tuple[str, ...]], Awaitable[BatchClassifierOutput]
]


@dataclass(frozen=True)
class ViewEvaluation:
    """한 text view와 classifier 결과의 추적 정보."""

    index: int
    view: TextView
    result: ClassifierResult
    latency_ms: float


@dataclass(frozen=True)
class ClassifierCallTrace:
    """한 classifier 호출에 포함된 view 위치와 전체 지연 시간."""

    index: int
    view_indices: tuple[int, ...]
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
    classifier_calls: tuple[ClassifierCallTrace, ...] = ()

    @property
    def evaluated_view_count(self) -> int:
        return len(self.evaluations)

    @property
    def classifier_call_count(self) -> int:
        return len(self.classifier_calls)


class ClassifierExecutionError(RuntimeError):
    """classifier 호출이나 반환값 검증 실패를 view 위치와 함께 전달한다."""

    def __init__(self, view_index: int, error_type: str) -> None:
        self.view_index = view_index
        self.error_type = error_type
        super().__init__(
            f"classifier 실행 실패(view_index={view_index}, error_type={error_type})"
        )


class BatchClassifierOutputError(ValueError):
    """batch classifier가 입력 view 수와 다른 개수의 결과를 반환했다."""

    def __init__(self, expected_count: int, actual_count: int) -> None:
        self.expected_count = expected_count
        self.actual_count = actual_count
        super().__init__(
            "batch classifier 결과 수 불일치"
            f"(expected={expected_count}, actual={actual_count})"
        )


def _normalize_output(output: ClassifierOutput) -> ClassifierResult:
    if isinstance(output, bool):
        return ClassifierResult(block=output)
    if isinstance(output, ClassifierResult):
        return output
    raise TypeError("classifier는 bool 또는 ClassifierResult를 반환해야 합니다.")


def _normalize_batch_output(
    output: BatchClassifierOutput,
    expected_count: int,
) -> tuple[tuple[ClassifierResult, Exception | None], ...]:
    if isinstance(output, (str, bytes)):
        raise TypeError("batch classifier는 판정 iterable을 반환해야 합니다.")
    try:
        items = tuple(output)
    except TypeError as exc:
        raise TypeError("batch classifier는 판정 iterable을 반환해야 합니다.") from exc
    if len(items) != expected_count:
        raise BatchClassifierOutputError(expected_count, len(items))

    normalized: list[tuple[ClassifierResult, Exception | None]] = []
    for item in items:
        try:
            normalized.append((_normalize_output(item), None))
        except Exception as exc:
            normalized.append(
                (
                    ClassifierResult(block=None, error=type(exc).__name__),
                    exc,
                )
            )
    return tuple(normalized)


def _failed_batch(
    exc: Exception,
    count: int,
) -> tuple[tuple[ClassifierResult, Exception], ...]:
    return tuple(
        (ClassifierResult(block=None, error=type(exc).__name__), exc)
        for _ in range(count)
    )


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


def _resolve_batch_size(total_view_count: int, batch_size: int | None) -> int:
    if batch_size is None:
        return max(total_view_count, 1)
    if isinstance(batch_size, bool) or not isinstance(batch_size, int):
        raise TypeError("batch_size는 int 또는 None이어야 합니다.")
    if batch_size < 1:
        raise ValueError("batch_size는 1 이상이어야 합니다.")
    return batch_size


@dataclass
class _EvaluationAccumulator:
    """동기·비동기 실행 경로가 공유하는 판정 정책 상태."""

    gateway_result: GatewayResult
    error_mode: ClassifierErrorMode
    stop_on_block: bool
    evaluations: list[ViewEvaluation] = field(default_factory=list)
    classifier_errors: list[str] = field(default_factory=list)
    classifier_calls: list[ClassifierCallTrace] = field(default_factory=list)
    blocked: bool = False
    category: str | None = None
    decision_source: Literal["classifier", "error_policy", "no_block"] = "no_block"
    trigger_view_index: int | None = None

    def record_call(self, view_indices: tuple[int, ...], latency_ms: float) -> None:
        self.classifier_calls.append(
            ClassifierCallTrace(len(self.classifier_calls), view_indices, latency_ms)
        )

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
            classifier_calls=tuple(self.classifier_calls),
        )


def _record_batch(
    accumulator: _EvaluationAccumulator,
    indexed_views: tuple[tuple[int, TextView], ...],
    results: tuple[tuple[ClassifierResult, Exception | None], ...],
    latency_ms: float,
) -> bool:
    accumulator.record_call(tuple(index for index, _ in indexed_views), latency_ms)
    should_stop = False
    for (index, view), (result, cause) in zip(indexed_views, results):
        should_stop = (
            accumulator.record(index, view, result, latency_ms, cause) or should_stop
        )
    return should_stop


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
        accumulator.record_call((index,), latency_ms)
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
        accumulator.record_call((index,), latency_ms)
        if accumulator.record(index, view, result, latency_ms, cause):
            break

    return accumulator.finish()


def evaluate_gateway_batch(
    gateway_result: GatewayResult,
    classifier: BatchGuardrailClassifier,
    *,
    error_mode: ClassifierErrorMode = "raise",
    stop_on_block: bool = True,
    batch_size: int | None = None,
) -> GatewayEvaluation:
    """Gateway view를 bounded batch로 판정하고 호출 단위 trace를 반환한다."""
    _validate_execution_options(classifier, error_mode, stop_on_block)
    resolved_batch_size = _resolve_batch_size(len(gateway_result.views), batch_size)
    accumulator = _EvaluationAccumulator(gateway_result, error_mode, stop_on_block)

    indexed_views = tuple(enumerate(gateway_result.views))
    for start in range(0, len(indexed_views), resolved_batch_size):
        batch = indexed_views[start : start + resolved_batch_size]
        texts = tuple(view.text for _, view in batch)
        started = time.perf_counter()
        try:
            results = _normalize_batch_output(classifier(texts), len(batch))
        except Exception as exc:
            results = _failed_batch(exc, len(batch))
        latency_ms = (time.perf_counter() - started) * 1000
        if _record_batch(accumulator, batch, results, latency_ms):
            break

    return accumulator.finish()


async def evaluate_gateway_batch_async(
    gateway_result: GatewayResult,
    classifier: AsyncBatchGuardrailClassifier,
    *,
    error_mode: ClassifierErrorMode = "raise",
    stop_on_block: bool = True,
    batch_size: int | None = None,
) -> GatewayEvaluation:
    """Gateway view를 async bounded batch로 순차 판정한다."""
    _validate_execution_options(classifier, error_mode, stop_on_block)
    resolved_batch_size = _resolve_batch_size(len(gateway_result.views), batch_size)
    accumulator = _EvaluationAccumulator(gateway_result, error_mode, stop_on_block)

    indexed_views = tuple(enumerate(gateway_result.views))
    for start in range(0, len(indexed_views), resolved_batch_size):
        batch = indexed_views[start : start + resolved_batch_size]
        texts = tuple(view.text for _, view in batch)
        started = time.perf_counter()
        try:
            output = await classifier(texts)
            results = _normalize_batch_output(output, len(batch))
        except Exception as exc:
            results = _failed_batch(exc, len(batch))
        latency_ms = (time.perf_counter() - started) * 1000
        if _record_batch(accumulator, batch, results, latency_ms):
            break

    return accumulator.finish()


__all__ = [
    "AsyncBatchGuardrailClassifier",
    "AsyncGuardrailClassifier",
    "BatchClassifierOutput",
    "BatchClassifierOutputError",
    "BatchGuardrailClassifier",
    "ClassifierErrorMode",
    "ClassifierExecutionError",
    "ClassifierOutput",
    "ClassifierResult",
    "ClassifierCallTrace",
    "GatewayEvaluation",
    "GuardrailClassifier",
    "ViewEvaluation",
    "evaluate_gateway",
    "evaluate_gateway_async",
    "evaluate_gateway_batch",
    "evaluate_gateway_batch_async",
]
