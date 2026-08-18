# 가드레일 실행·집계 API

`Gateway.evaluate()`, `Gateway.evaluate_async()`와 batch 변형은 정규화·후보 생성 결과를 호출자가
제공한 classifier에 순서대로 전달하고, 하나라도 block이면 최종 block하는 OR 정책을 적용한다. 특정
모델 SDK, Torch, Transformers나 네트워크 클라이언트에 의존하지 않는다.

## 최소 사용법

classifier는 문자열을 받아 `bool`을 반환하는 동기 callable이면 된다.

```python
from k_safeguard import Gateway

def classifier(text: str) -> bool:
    return external_guardrail(text) == "unsafe"

result = Gateway().evaluate("사용자 입력", classifier)

if result.block:
    raise PermissionError("guardrail blocked")
```

기본값은 첫 block에서 평가를 중단한다. 초성 provider처럼 여러 view를 사용하는 경우 뒤쪽 모델 호출을
생략할 수 있다. 모든 view의 관측 결과가 필요하면 `stop_on_block=False`를 지정한다.

## 비동기 classifier

원격 API나 async 웹 프레임워크에서는 문자열을 받아 awaitable 판정을 반환하는 classifier를
`Gateway.evaluate_async()`에 전달한다.

```python
from k_safeguard import Gateway

async def classifier(text: str) -> bool:
    response = await guardrail_client.classify(text=text)
    return response.blocked

result = await Gateway().evaluate_async(
    "사용자 입력",
    classifier,
    error_mode="block",
)
```

비동기 API도 view 순서, OR 집계, `stop_on_block`과 `error_mode` 계약이 동기 API와 같다. view를
동시에 호출하지 않고 순차적으로 await하므로 첫 block 조기 종료가 보장되고, 로컬 모델이나 호출량 제한이
있는 원격 API에 갑작스러운 병렬 부하를 만들지 않는다. 여러 요청 자체의 동시성은 웹 서버나 호출자가
관리하고, 한 요청 안의 batch 실행은 별도 후속 API로 다룬다.

동기 classifier는 `evaluate()`에, async classifier는 `evaluate_async()`에 전달해야 한다. 비동기
classifier가 반환한 `bool`과 `ClassifierResult`는 동기 API와 동일하게 정규화된다. task 취소는
classifier 오류로 변환하지 않고 호출자에게 전파한다.

## Batch classifier

로컬 Transformer나 batch endpoint처럼 여러 view를 한 호출로 판정할 수 있는 모델은
`Gateway.evaluate_batch()`에 연결한다. classifier는 정렬된 문자열 `tuple`을 받고 같은 개수와 순서의
`bool` 또는 `ClassifierResult` iterable을 반환해야 한다.

```python
from k_safeguard import Gateway

def batch_classifier(texts: tuple[str, ...]):
    outputs = local_guardrail.classify_batch(texts)
    return [output.blocked for output in outputs]

result = Gateway().evaluate_batch(
    "사용자 입력",
    batch_classifier,
    batch_size=4,
    error_mode="block",
)
```

async batch endpoint는 `Gateway.evaluate_batch_async()`를 사용한다.

```python
async def batch_classifier(texts: tuple[str, ...]):
    response = await guardrail_client.classify_batch(texts=texts)
    return [item.blocked for item in response.items]

result = await Gateway().evaluate_batch_async(
    "사용자 입력",
    batch_classifier,
    batch_size=4,
)
```

`batch_size=None`은 생성된 모든 view를 한 번에 호출한다. 양의 정수를 지정하면 view 순서를 유지한 채
bounded chunk로 나눈다. 한 chunk는 이미 모델에 전달됐으므로 그 안에서 block이 발견돼도 chunk의 모든
결과를 trace에 남기고, `stop_on_block=True`이면 다음 chunk부터 생략한다. 따라서 모든 view가 한
batch에 들어간 경우 block이 있어도 `stopped_early=False`일 수 있다.

batch 호출 예외와 입력·출력 개수 불일치는 그 호출에 포함된 모든 view의 classifier 오류다. 개수
불일치는 `BatchClassifierOutputError`로 구분한다. 출력 개수는 맞지만 특정 항목만 잘못된 타입이면 해당
view만 오류 정책을 적용하고 나머지 유효한 판정은 보존한다. async batch의 task 취소는 일반 async
API와 마찬가지로 호출자에게 전파한다.

## 구조화된 판정

category와 모델 metadata를 보존하려면 `ClassifierResult`를 반환한다.

```python
from k_safeguard import ClassifierResult, Gateway

def classifier(text: str) -> ClassifierResult:
    output = my_guardrail.classify(text)
    return ClassifierResult(
        block=output.block,
        category=output.category,
        metadata=(("model_revision", output.revision),),
    )

result = Gateway().evaluate("사용자 입력", classifier)
print(result.block, result.category, result.trigger_view_index)

for trace in result.evaluations:
    print(trace.index, trace.view.kind, trace.result.block, trace.latency_ms)
```

`GatewayEvaluation`에는 전처리 결과, 실제 평가한 view trace, 최종 category, 최초 trigger view,
classifier 오류와 조기 종료 여부가 함께 들어 있다.

`classifier_calls`에는 실제 classifier 호출별 `view_indices`와 전체 `latency_ms`가 기록된다. 단일 view
API에서는 view 하나가 호출 하나에 대응하고, batch API에서는 여러 view가 같은 호출을 가리킨다. batch
평가의 각 `ViewEvaluation.latency_ms`는 자신이 포함된 호출의 전체 지연 시간을 공유하므로, 총 모델
지연 시간은 view latency를 합산하지 말고 `classifier_calls`를 합산해야 한다.

`decision_source`는 실제 block을 만든 원인이 `classifier`인지 `error_policy`인지 나타낸다. block이
없으면 classifier 오류 포함 여부와 관계없이 `no_block`이므로, 안전 판정과 실행 장애를 구분하려면
반드시 `classifier_errors`도 함께 확인한다.

## 오류 정책

classifier 예외와 `ClassifierResult(block=None, error="...")`는 정상 safe 판정으로 취급하지 않는다.

| `error_mode` | 동작 | 권장 용도 |
|---|---|---|
| `raise` | `ClassifierExecutionError` 발생 | 기본값, 호출자가 장애 정책을 결정 |
| `block` | 오류를 block으로 처리 | fail-closed 보안 경계 |
| `allow` | 오류를 기록하고 다음 view 계속 평가 | 별도 장애 격리가 있는 fail-open 환경 |

```python
result = Gateway().evaluate(
    "사용자 입력",
    classifier,
    error_mode="block",
)
```

예외 메시지는 입력이나 외부 SDK의 상세 오류를 복사하지 않고 예외 타입과 view index만 노출한다.
classifier가 명시적으로 반환한 `error` 문자열은 trace에 보존되므로 민감정보를 넣지 않아야 한다.

## provider 오류와 classifier 오류

- candidate provider 오류는 기존 `GatewayResult.provider_errors`에 기록된다.
- `strict_providers=True`이면 provider 예외를 즉시 전파한다.
- classifier 오류는 `error_mode`에 따라 처리하고 `GatewayEvaluation.classifier_errors`에 기록한다.

두 오류 경계는 분리되어 있어 후보 provider 하나가 실패해도 기본 정책에서는 원문·무손실 view를
가드레일로 검사할 수 있다.

## 로컬 Kanana 연결 예시

저장소의 실험용 `KananaPromptAdapter`는 callable 계약을 직접 구현한다. 모델 가중치와
Torch·Transformers는 core wheel이 아니라 실험 환경에서만 관리한다.

```python
from pathlib import Path

from experiments.benchmark.adapters import KananaPromptAdapter
from k_safeguard import Gateway

adapter = KananaPromptAdapter(
    model_path=Path(r"D:\local llm\guardrails\models\kanana-prompt-2.1b"),
    model_id="kakaocorp/kanana-safeguard-prompt-2.1b",
    revision="167d74d4706b236580b0e48318337c7ac6ba7848",
)
result = Gateway().evaluate("사용자 입력", adapter, error_mode="block")
```

로컬 설치를 바로 확인하려면 [`experiments/guardrail/run_gateway.py`](../experiments/guardrail/run_gateway.py)를
사용한다. 이 adapter는 패키지 공개 API가 아니라 특정 모델을 재현하기 위한 reference implementation이다.

## 현재 경계

- 동기·비동기 단일 view 및 bounded batch classifier API를 제공하며, candidate provider 생성은 동기 방식이다.
- batch chunk는 순차 실행한다. chunk 병렬화, retry와 circuit breaker는 호출자 또는 adapter 계층의 책임이다.
- 기본 Gateway는 여전히 무손실 정규화만 활성화하며 lossy provider는 명시적으로 주입해야 한다.
- `error_mode="allow"`는 보안 경계를 약화할 수 있으므로 서비스 위협 모델에 따라 선택한다.
