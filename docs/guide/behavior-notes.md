# 동작과 주의점

코드를 작성할 때 놓치기 쉬운 동작을 모았습니다.

## `normalize()`는 확신도 없는 후보를 고르지 않습니다

`SpacedJamoProvider`와 `LiaisonInverseProvider`의 후보는 `confidence=None`입니다. 이 두 provider만 넣으면
`normalize()` 결과는 무손실 정규화와 같습니다. 후보를 쓰려면 `process()`나 `evaluate()`를 호출합니다.

## `max_views`를 너무 작게 잡으면 판정에서 빠집니다

`max_views=1`이면 정규화 view가 잘려 원문만 판정합니다. `truncated`가 `True`인지 확인합니다.

```python
Gateway(max_views=1).evaluate("ㅇㅏㄴ", lambda text: text == "안").block   # False
```

앞선 provider가 예산을 먼저 쓰므로 뒤 provider의 후보가 잘릴 수 있습니다.

## `decision_source`는 처음 차단을 결정한 근거입니다

`error_mode="block"`, `stop_on_block=False`에서 앞 view가 오류를 내고 뒤 view를 분류기가 차단해도
`decision_source`는 `error_policy`이고 `category`는 `None`입니다. 분류기 판정이 필요하면 `evaluations`를 확인합니다.

## 초성체는 복원하지 않습니다

`ㅇㅋ` 같은 초성체는 원문 정보가 대부분 사라진 표기라 그대로 둡니다.

## 긴 입력

`MlRestoreProvider`는 입력을 조각으로 나눠 복원하며, 조각 수 상한을 넘은 뒷부분은 그대로 둡니다. 상한은
[`MAX_CHUNKS`][k_safeguard.providers.ml_restore.MAX_CHUNKS]와 manifest의 `max_chars`로 정해집니다.
후보의 metadata `restored_chars`와 `input_chars`를 비교하면 잘렸는지 알 수 있습니다. 앞부분에 바꿀 글자가 없으면
후보 자체가 나오지 않으므로, 입력이 이 상한을 넘을 수 있으면 길이를 직접 제한하세요.
