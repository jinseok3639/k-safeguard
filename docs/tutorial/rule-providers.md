# 규칙 provider

무손실로 확정할 수 없는 표기는 provider를 직접 넣어야 후보가 생깁니다. 두 규칙 provider는 추가 의존성이 없습니다.
둘 다 `confidence=None`이라 `normalize()`는 이 후보를 고르지 않으므로, `process()`나 `evaluate()`와 함께 씁니다.

## 띄어 쓴 자모: `SpacedJamoProvider`

공백으로 띄어 쓴 자모 구간이 완성형 음절로 전부 조합될 때 후보 하나를 만듭니다.

```python
from k_safeguard import Gateway
from k_safeguard.providers.spaced_jamo import SpacedJamoProvider

gateway = Gateway(providers=[SpacedJamoProvider()])
[view.text for view in gateway.process("ㅅ ㅣ ㅅ ㅡ ㅌ ㅔ ㅁ 점검").views]
# ['ㅅ ㅣ ㅅ ㅡ ㅌ ㅔ ㅁ 점검', '시스템 점검']
```

!!! warning "어절 경계가 사라집니다"
    이어진 자모 구간은 한 덩어리로 합쳐집니다. `ㅅ ㅣ ㅅ ㅡ ㅌ ㅔ ㅁ ㅍ ㅡ ㄹ ...`은 `시스템프롬...`이 되어,
    공백을 포함한 키워드와는 일치하지 않습니다.

## 연음: `LiaisonInverseProvider`

연음으로 적었을 때의 원래 철자 조합을 나열합니다. 어느 후보가 맞는지는 판단하지 않습니다.

```python
from k_safeguard import Gateway
from k_safeguard.providers import LiaisonInverseProvider

gateway = Gateway(providers=[LiaisonInverseProvider(max_candidates=9)])
gateway.evaluate("머글게", lambda text: "먹을게" in text).block   # True
```

!!! warning "정상 문장에서도 후보가 나옵니다"
    `바다에 가다`에서도 `받아에 가다`, `바다에 갇아`가 나옵니다. 분류기 오탐과 호출 수가 늘 수 있습니다.

??? example "전체 예제: `examples/07_liaison_provider.py`"

    ```python
    --8<-- "examples/07_liaison_provider.py"
    ```

참고: [Provider 레퍼런스](../reference/providers.md)
