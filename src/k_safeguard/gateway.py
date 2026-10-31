"""모델에 종속되지 않는 경량 text gateway API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, Protocol, runtime_checkable

from .normalization import NormalizationResult, normalize_korean


if TYPE_CHECKING:
    from .execution import (
        AsyncBatchTextClassifier,
        AsyncTextClassifier,
        BatchTextClassifier,
        ClassifierErrorMode,
        GatewayEvaluation,
        TextClassifier,
    )


Metadata = tuple[tuple[str, str], ...]
DEFAULT_MAX_VIEWS = 10


@dataclass(frozen=True)
class CandidateProposal:
    """선택형 provider가 제안하는 하나의 lossy text view."""

    text: str
    lossy: bool = True
    confidence: float | None = None
    metadata: Metadata = ()


@runtime_checkable
class CandidateProvider(Protocol):
    """외부 형태소 분석기나 복원기를 연결하기 위한 최소 protocol."""

    name: str

    def generate(self, text: str) -> Iterable[CandidateProposal]:
        """입력에서 0개 이상의 후보 view를 생성한다."""


@dataclass(frozen=True)
class TextView:
    """하위 시스템에 전달할 수 있는 원문·정규화문·후보문 view."""

    text: str
    kind: str
    provider: str
    lossy: bool
    confidence: float | None
    metadata: Metadata = ()


@dataclass(frozen=True)
class GatewayResult:
    """무손실 정규화 결과와 opt-in 후보 view 묶음."""

    original: str
    normalization: NormalizationResult
    views: tuple[TextView, ...]
    provider_errors: tuple[str, ...]
    truncated: bool

    @property
    def normalized(self) -> str:
        return self.normalization.text

    @property
    def changed(self) -> bool:
        return self.normalization.changed

    @property
    def has_lossy_views(self) -> bool:
        return any(view.lossy for view in self.views)


class Gateway:
    """기본 설치에서는 무손실 정규화만 수행하는 model-agnostic gateway."""

    def __init__(
        self,
        *,
        providers: Iterable[CandidateProvider] = (),
        max_views: int = DEFAULT_MAX_VIEWS,
        strict_providers: bool = False,
    ) -> None:
        if max_views < 1:
            raise ValueError("max_views는 1 이상이어야 합니다.")
        self._providers = tuple(providers)
        self._max_views = max_views
        self._strict_providers = strict_providers

    def process(self, text: str) -> GatewayResult:
        normalization = normalize_korean(text)
        views = [TextView(text, "original", "core", False, 1.0)]
        seen = {text}
        truncated = False
        if normalization.text not in seen:
            if len(views) < self._max_views:
                views.append(
                    TextView(
                        normalization.text,
                        "normalized",
                        "core",
                        False,
                        normalization.confidence,
                        (("rules", ",".join(normalization.applied_rules)),),
                    )
                )
                seen.add(normalization.text)
            else:
                truncated = True

        errors: list[str] = []
        for provider in self._providers:
            provider_name = getattr(provider, "name", type(provider).__name__)
            try:
                proposals = provider.generate(normalization.text)
                for proposal in proposals:
                    if not isinstance(proposal, CandidateProposal):
                        raise TypeError("provider는 CandidateProposal을 반환해야 합니다.")
                    if not isinstance(proposal.text, str):
                        raise TypeError("candidate text는 str이어야 합니다.")
                    if proposal.confidence is not None and not 0 <= proposal.confidence <= 1:
                        raise ValueError("candidate confidence는 0~1이어야 합니다.")
                    if proposal.text in seen:
                        continue
                    if len(views) >= self._max_views:
                        truncated = True
                        break
                    views.append(
                        TextView(
                            proposal.text,
                            "candidate",
                            provider_name,
                            proposal.lossy,
                            proposal.confidence,
                            proposal.metadata,
                        )
                    )
                    seen.add(proposal.text)
            except Exception as exc:
                if self._strict_providers:
                    raise
                errors.append(f"{provider_name}:{type(exc).__name__}")

        return GatewayResult(
            original=text,
            normalization=normalization,
            views=tuple(views),
            provider_errors=tuple(errors),
            truncated=truncated,
        )

    def normalize(self, text: str) -> str:
        """정규화된 문장 하나를 돌려준다.

        확신도를 낸 provider 후보 중 가장 높은 것을 고르고, 없으면 무손실 정규화 결과를 준다.
        확신도가 없는 후보(연음 나열 등)는 어느 것이 맞는지 알 수 없어 고르지 않는다. 후보를
        직접 비교하거나 원문까지 함께 검사하려면 :meth:`process`를 쓴다.
        """
        result = self.process(text)
        candidates = [
            view
            for view in result.views
            if view.kind == "candidate" and view.confidence is not None
        ]
        if not candidates:
            return result.normalized
        return max(candidates, key=lambda view: view.confidence).text

    def evaluate(
        self,
        text: str,
        classifier: TextClassifier,
        *,
        error_mode: ClassifierErrorMode = "raise",
        stop_on_block: bool = True,
    ) -> GatewayEvaluation:
        """생성한 view를 classifier로 판정하고 OR 결과와 trace를 반환한다."""
        from .execution import evaluate_gateway

        return evaluate_gateway(
            self.process(text),
            classifier,
            error_mode=error_mode,
            stop_on_block=stop_on_block,
        )

    async def evaluate_async(
        self,
        text: str,
        classifier: AsyncTextClassifier,
        *,
        error_mode: ClassifierErrorMode = "raise",
        stop_on_block: bool = True,
    ) -> GatewayEvaluation:
        """생성한 view를 async classifier로 순차 판정하고 trace를 반환한다."""
        from .execution import evaluate_gateway_async

        return await evaluate_gateway_async(
            self.process(text),
            classifier,
            error_mode=error_mode,
            stop_on_block=stop_on_block,
        )

    def evaluate_batch(
        self,
        text: str,
        classifier: BatchTextClassifier,
        *,
        error_mode: ClassifierErrorMode = "raise",
        stop_on_block: bool = True,
        batch_size: int | None = None,
    ) -> GatewayEvaluation:
        """생성한 view를 bounded batch classifier로 판정한다."""
        from .execution import evaluate_gateway_batch

        return evaluate_gateway_batch(
            self.process(text),
            classifier,
            error_mode=error_mode,
            stop_on_block=stop_on_block,
            batch_size=batch_size,
        )

    async def evaluate_batch_async(
        self,
        text: str,
        classifier: AsyncBatchTextClassifier,
        *,
        error_mode: ClassifierErrorMode = "raise",
        stop_on_block: bool = True,
        batch_size: int | None = None,
    ) -> GatewayEvaluation:
        """생성한 view를 async bounded batch classifier로 판정한다."""
        from .execution import evaluate_gateway_batch_async

        return await evaluate_gateway_batch_async(
            self.process(text),
            classifier,
            error_mode=error_mode,
            stop_on_block=stop_on_block,
            batch_size=batch_size,
        )


__all__ = [
    "DEFAULT_MAX_VIEWS",
    "CandidateProposal",
    "CandidateProvider",
    "Gateway",
    "GatewayResult",
    "TextView",
]
