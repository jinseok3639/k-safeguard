# 문장 정규화

입력을 정리해 문자열 하나로 받으려면 `Gateway.normalize()`를 씁니다. 기존 파이프라인에 한 줄로 끼울 수 있습니다.

```python
from k_safeguard import Gateway

gateway = Gateway()
query = gateway.normalize("ㅎㅘㄴㅂㅜㄹ 규정")   # '환불 규정'
results = search_index.search(query)
```

## 무엇을 되돌리나요

기본 경로는 의미가 바뀌지 않는 표기 변형만 되돌립니다.

| 입력 | 결과 | 규칙 |
|---|---|---|
| 한글 사이의 U+200B | 제거 | `remove_hangul_zwsp` |
| 반각 자모 `U+FFB1 U+FFC2 U+FFA4` | `만` | `normalize_halfwidth_hangul` |
| 조합형 자모 `U+110B U+1161 U+11AB` | `안` | `compose_modern_jamo` |
| 호환 자모 `ㅇㅓㅂㅅㅇㅓ` | `없어` | `compose_compat_jamo` |

초성체(`ㅇㅋ`), 독립 자모(`ㅋㅋㅋ`), 된소리, 연음, 띄어쓰기는 문맥 없이 확정할 수 없어 그대로 둡니다.
ZWNJ, ZWJ 같은 다른 format 문자와 이모지, 한영 혼용 입력도 보존합니다.

## 변경 위치까지 기록하기

로그나 감사 기록에 무엇을 바꿨는지 남기려면 `normalize_korean()`을 직접 호출합니다. 위치는 원문 기준입니다.

```python
from k_safeguard import normalize_korean

result = normalize_korean("계좌​번호 ㅂㅣㅁㅣㄹㅂㅓㄴㅎㅗ")

result.text            # '계좌번호 비밀번호'
result.applied_rules   # ('remove_hangul_zwsp', 'compose_compat_jamo')
result.edits[1]
# rule_id='compose_compat_jamo', source_start=6, source_end=16,
# before='ㅂㅣㅁㅣㄹㅂㅓㄴㅎㅗ', after='비밀번호', ...
```

??? example "전체 예제: `examples/01_normalize_basics.py`"

    ```python
    --8<-- "examples/01_normalize_basics.py"
    ```

참고: [`normalize_korean`][k_safeguard.normalization.normalize_korean],
[`Gateway.normalize`][k_safeguard.gateway.Gateway.normalize]
