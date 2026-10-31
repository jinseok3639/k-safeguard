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
"""원문을 포함한 view 수의 기본 상한."""


@dataclass(frozen=True)
class CandidateProposal:
    """선택형 provider가 제안하는 하나의 lossy text view.

    Attributes:
        text: 후보 문장.
        lossy: 원문 정보를 잃을 수 있는 변환인지.
        confidence: 0~1 확신도. `None`이면 `Gateway.normalize`가 고르지 않는다.
        metadata: 후보에 붙일 `(키, 값)` 목록.
    """

    text: str
    lossy: bool = True
    confidence: float | None = None
    metadata: Metadata = ()


@runtime_checkable
class CandidateProvider(Protocol):
    """외부 형태소 분석기나 복원기를 연결하기 위한 최소 protocol.

    상속 없이 `name` 속성과 `generate` 메서드만 갖추면 된다.

    Attributes:
        name: `TextView.provider`와 `provider_errors`에 남는 이름.
    """

    name: str

    def generate(self, text: str) -> Iterable[CandidateProposal]:
        """입력에서 0개 이상의 후보 view를 생성한다.

        Args:
            text: 무손실 정규화를 마친 문자열. 원문이 아니다.

        Returns:
            후보 목록. 제안할 것이 없으면 비어 있다.
        """


@dataclass(frozen=True)
class TextView:
    """하위 시스템에 전달할 수 있는 원문·정규화문·후보문 view.

    Attributes:
        text: view 문장.
        kind: `original`, `normalized`, `candidate` 중 하나.
        provider: 무손실 경로는 `core`, 후보는 provider 이름.
        lossy: 원문 정보를 잃을 수 있는 view인지.
        confidence: 0~1 확신도. 모르면 `None`.
        metadata: 적용 규칙이나 provider 정보의 `(키, 값)` 목록.
    """

    text: str
    kind: str
    provider: str
    lossy: bool
    confidence: float | None
    metadata: Metadata = ()


@dataclass(frozen=True)
class GatewayResult:
    """무손실 정규화 결과와 opt-in 후보 view 묶음.

    Attributes:
        original: 입력 원문.
        normalization: 무손실 정규화 상세.
        views: 원문, 정규화문, 후보 순서의 view. 원문이 항상 첫 번째다.
        provider_errors: 실패한 provider의 `이름:예외타입` 목록.
        truncated: `max_views` 때문에 잘린 view가 있는지.
    """

    original: str
    normalization: NormalizationResult
    views: tuple[TextView, ...]
    provider_errors: tuple[str, ...]
    truncated: bool

    @property
    def normalized(self) -> str:
        """무손실 정규화 문장."""
        return self.normalization.text

    @property
    def changed(self) -> bool:
        """무손실 정규화가 원문을 바꿨는지."""
        return self.normalization.changed

    @property
    def has_lossy_views(self) -> bool:
        """lossy view가 하나라도 있는지."""
        return any(view.lossy for view in self.views)


class Gateway:
    """기본 설치에서는 무손실 정규화만 수행하는 model-agnostic gateway.

    Args:
        providers: 후보를 만들 provider. 선언 순서대로 실행한다.
        max_views: 원문을 포함한 view 수 상한.
        strict_providers: `True`면 provider 예외를 그대로 올린다. `False`면
            `provider_errors`에 기록하고 계속한다.

    Raises:
        ValueError: `max_views`가 1 미만일 때.
    """

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
        """원문, 정규화문, provider 후보를 모두 만든다.

        provider는 정규화문을 입력으로 받으며 서로 체이닝되지 않는다. 같은 텍스트의 view는
        하나만 남는다.

        Args:
            text: 입력 문장.

        Returns:
            view 묶음과 변경 내역.
        """
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
        """생성한 view를 classifier로 판정하고 OR 결과와 trace를 반환한다.

        Args:
            text: 입력 문장.
            classifier: 문자열을 받아 `bool` 또는 `ClassifierResult`를 돌려주는 callable.
                `True`가 차단이다.
            error_mode: 분류기 오류 정책. `raise`, `block`, `allow` 중 하나.
            stop_on_block: 첫 차단에서 남은 view를 생략할지.

        Returns:
            최종 판정과 view별 trace.

        Raises:
            ClassifierExecutionError: `error_mode="raise"`에서 분류기가 실패했을 때.
        """
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
        """생성한 view를 async classifier로 순차 판정하고 trace를 반환한다.

        인자와 반환은 :meth:`evaluate`와 같다. view를 동시에 보내지 않는다.
        """
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
        """생성한 view를 bounded batch classifier로 판정한다.

        Args:
            text: 입력 문장.
            classifier: 문자열 튜플을 받아 같은 개수의 판정을 돌려주는 callable.
            error_mode: 분류기 오류 정책. `raise`, `block`, `allow` 중 하나.
            stop_on_block: 차단이 나오면 다음 묶음을 생략할지. 이미 넘긴 묶음은 모두 기록한다.
            batch_size: 한 번에 넘길 view 수. `None`이면 전체를 한 번에 넘긴다.

        Returns:
            최종 판정과 view별·호출별 trace.

        Raises:
            ClassifierExecutionError: `error_mode="raise"`에서 분류기가 실패했을 때.
            ValueError: `batch_size`가 1 미만일 때.
            TypeError: `batch_size`가 `int`나 `None`이 아닐 때.
        """
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
        """생성한 view를 async bounded batch classifier로 판정한다.

        인자와 반환은 :meth:`evaluate_batch`와 같다. 묶음 사이는 순차로 처리한다.
        """
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
