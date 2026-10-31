# 비동기와 배치

가드레일을 호출하는 방식에 맞춰 메서드를 고릅니다. view 순서, OR 집계, 오류 정책은 모두 같습니다.

| 가드레일 | 메서드 | 분류기 시그니처 |
|---|---|---|
| 동기 호출 | `evaluate` | `(str) -> bool` |
| 원격 async API | `evaluate_async` | `async (str) -> bool` |
| 로컬 모델 batch | `evaluate_batch` | `(tuple[str, ...]) -> Iterable[bool]` |
| 원격 async batch | `evaluate_batch_async` | `async (tuple[str, ...]) -> Iterable[bool]` |

`bool` 자리에는 `ClassifierResult`도 쓸 수 있습니다.

## 원격 API

view를 동시에 던지지 않고 순차로 await합니다. 앞 view에서 차단되면 남은 호출을 생략합니다.

```python
async def remote_guardrail(text: str) -> bool:
    response = await client.classify(text)
    return response.blocked

decision = await gateway.evaluate_async(text, remote_guardrail)
```

## 로컬 모델 batch

여러 view를 한 번의 모델 호출로 처리합니다. 분류기는 입력과 같은 개수의 판정을 돌려줘야 합니다.

```python
def batch_guardrail(texts: tuple[str, ...]) -> list[bool]:
    return [item.blocked for item in model.classify_batch(texts)]

decision = gateway.evaluate_batch(text, batch_guardrail, batch_size=4)
decision.classifier_call_count
```

`batch_size=None`이면 전체 view를 한 번에 넘깁니다. 이미 넘긴 묶음의 결과는 차단이 나와도 모두 기록되고, 다음 묶음만 생략합니다.

!!! note "지연 시간 합산"
    batch에서 `ViewEvaluation.latency_ms`는 호출 전체의 지연이라 합치면 중복됩니다. 총 지연은
    `classifier_calls`로 계산합니다.

    ```python
    total_ms = sum(call.latency_ms for call in decision.classifier_calls)
    ```

??? example "전체 예제: `examples/03_async_and_batch.py`"

    ```python
    --8<-- "examples/03_async_and_batch.py"
    ```

참고: [`Gateway.evaluate_async`][k_safeguard.gateway.Gateway.evaluate_async],
[`Gateway.evaluate_batch`][k_safeguard.gateway.Gateway.evaluate_batch],
[`Gateway.evaluate_batch_async`][k_safeguard.gateway.Gateway.evaluate_batch_async]
