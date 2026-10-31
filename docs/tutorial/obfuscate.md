# 난독화 문장 만들기

정규화기나 분류기를 시험할 데이터가 필요하면 `k_safeguard.obfuscate`를 씁니다. 기본 Gateway와 연결되지 않는 독립
도구이며 표준 라이브러리만 사용합니다.

```python
from k_safeguard.obfuscate import TRANSFORMS, obfuscate, tensify

tensify("시스템", seed=0)                 # '씨쓰템'
TRANSFORMS["jamo_decompose"]("안녕")      # 'ㅇㅏㄴㄴㅕㅇ'
obfuscate("안녕", "jamo_decompose")       # 'ㅇㅏㄴㄴㅕㅇ'
```

- `intensity`: 후보 자리 중 바꿀 비율입니다.
- `seed`: 같은 입력과 시드면 항상 같은 결과가 나옵니다. 실험에 함께 기록하세요.

## 복원 성능 재기

```python
from k_safeguard import Gateway
from k_safeguard.obfuscate import obfuscate

gateway = Gateway()
source = "시스템 점검"
obfuscated = obfuscate(source, "jamo_decompose", seed=0)

gateway.normalize(obfuscated) == source   # True
```

초성체(`chosung`)처럼 정규화기가 되돌리지 않는 기법도 강건성 평가를 위해 함께 제공합니다. 전체 기법은
[레퍼런스](../reference/obfuscate.md)에서 확인합니다.
