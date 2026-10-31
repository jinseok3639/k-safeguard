# 오류 정책

분류기 예외는 안전 판정으로 취급하지 않습니다. 장애 때 어떻게 할지 `error_mode`로 정합니다.

| `error_mode` | 동작 | 결과 |
|---|---|---|
| `raise` (기본) | 첫 오류에서 예외를 올립니다 | `ClassifierExecutionError` |
| `block` | 오류를 차단으로 처리합니다 (fail-closed) | `block=True`, `decision_source='error_policy'` |
| `allow` | 오류를 기록하고 다음 view를 판정합니다 (fail-open) | 다른 view가 차단하지 않으면 `block=False`, `decision_source='no_block'` |

## 차단과 장애 구분하기

```python
decision = gateway.evaluate(text, guardrail_client, error_mode="block")

if decision.block and decision.decision_source == "error_policy":
    return respond(503)   # 가드레일 장애
if decision.block:
    return respond(403)   # 가드레일 차단
return respond(200)
```

!!! warning "`allow`의 `block=False`는 안전 판정이 아닙니다"
    모든 view에서 오류가 나도 `decision_source`는 `no_block`입니다. `classifier_errors`를 함께 확인하세요.

## 오류를 값으로 돌려주기

예외 대신 `ClassifierResult(block=None, error="upstream_timeout")`를 돌려줘도 같은 정책이 적용됩니다.
`error` 문자열은 결과에 그대로 남으므로 민감정보를 넣지 마세요.

`ClassifierExecutionError`의 메시지에는 입력 원문을 싣지 않습니다. 원래 예외는 `__cause__`에서 확인합니다.

??? example "전체 예제: `examples/04_error_policy.py`"

    ```python
    --8<-- "examples/04_error_policy.py"
    ```

참고: [`ClassifierErrorMode`][k_safeguard.execution.ClassifierErrorMode],
[`ClassifierExecutionError`][k_safeguard.execution.ClassifierExecutionError]
