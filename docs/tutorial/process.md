# 후보와 변경 내역 보기

복원문을 그대로 믿기 어려우면 `Gateway.process()`로 원문, 정규화문, 후보를 모두 받아 직접 고릅니다.

```python
from k_safeguard import Gateway
from k_safeguard.providers.spaced_jamo import SpacedJamoProvider

gateway = Gateway(providers=[SpacedJamoProvider()])
result = gateway.process("ㅎ ㅘ ㄴ ㅂ ㅜ ㄹ 규정")

[(view.kind, view.lossy, view.text) for view in result.views]
# [('original', False, 'ㅎ ㅘ ㄴ ㅂ ㅜ ㄹ 규정'),
#  ('candidate', True, '환불 규정')]

result.has_lossy_views   # True
result.truncated         # False
result.provider_errors   # ()
```

## view 순서

1. `original`: 원문입니다. 항상 `views[0]`입니다.
2. `normalized`: 무손실 정규화 결과입니다. 원문과 다를 때만 있습니다.
3. `candidate`: provider 후보입니다. 선언한 provider 순서대로 나옵니다.

같은 텍스트의 view는 하나만 남습니다. 전체 개수는 `max_views`로 제한되며, 넘치면 `truncated`가 `True`가 됩니다.

참고: [`Gateway.process`][k_safeguard.gateway.Gateway.process],
[`GatewayResult`][k_safeguard.gateway.GatewayResult], [`TextView`][k_safeguard.gateway.TextView]
