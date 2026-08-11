# 한국어 정규화기 MVP

`k_safeguard.normalization`은 기존 가드레일 앞단에서 정보 손실 없이 확정할 수 있는 한국어 표기 변형만
정규화하는 첫 번째 MVP다. 복원 모델을 사용하지 않으며, 모호한 입력은 원문을 유지한다.

## 지원 범위

| rule ID | 처리 대상 | 정책 |
|---|---|---|
| `remove_hangul_zwsp` | 한글·자모와 인접한 U+200B | 해당 문자만 제거 |
| `compose_modern_jamo` | `안` 같은 현대 조합형 자모열 | 명확한 초성+중성(+종성)을 음절로 조합 |
| `compose_compat_jamo` | `ㅇㅏㄴ` 같은 호환 자모열 | 다음 모음 경계를 확인해 음절로 조합 |

전역 Unicode NFC를 적용하지 않고 현대 한글 자모열만 직접 조합한다. 이렇게 하면 한글과 무관한
결합문자, emoji ZWJ sequence와 코드스위칭 입력을 임의로 바꾸지 않는다.

다음 항목은 문맥 없이는 원문을 확정할 수 없어 MVP에서 변경하지 않는다.

- 초성체
- 된소리·쌍자음화
- 연음·구개음화
- 띄어쓰기 파괴
- 일반 영문·숫자 사이의 zero-width 문자

초성체의 opt-in 다중 후보 생성기는 [`CHOSUNG_CANDIDATES.md`](./CHOSUNG_CANDIDATES.md)를 참고한다.
된소리화의 opt-in bounded 역변형 후보는
[`TENSIFY_CANDIDATES.md`](./experiments/benchmark/TENSIFY_CANDIDATES.md)를 참고한다.
기본 `normalize_korean()`에는 연결하지 않아 무손실 동작과 clean mutation 0% 경계를 유지한다.

## 사용법

```python
from k_safeguard import normalize_korean

result = normalize_korean("ㅇ\u200bㅏㄴㄴㅕㅇ")

assert result.text == "안녕"
assert result.changed is True
assert result.lossy is False
print(result.applied_rules)
print(result.edits)
```

`NormalizationResult`는 다음 정보를 반환한다.

- `original`, `text`: 원문과 정규화 결과
- `changed`, `lossy`, `confidence`: 변경·정보 손실·신뢰도
- `applied_rules`: 실제 결과를 바꾼 rule ID
- `edits`: 원문 기준 위치, 변경 전후 문자열과 rule ID
- `errors`: 행 단위 처리 오류를 위한 필드
- `version`: 정규화 알고리즘 버전

## 벤치마크 검증

2026-08-08에 `hf_repo/benchmark.jsonl` 5,555행 전체를 실행했다.

| technique | intensity | n | 정확 복원 | 실제 변경 | 오류 |
|---|---:|---:|---:|---:|---:|
| clean | 0 | 505 | 505 | 0 | 0 |
| `jamo_decompose` | 0.5 | 505 | 505 | 504 | 0 |
| `jamo_decompose` | 1.0 | 505 | 505 | 504 | 0 |
| `zwsp_inject` | 0.5 | 505 | 505 | 504 | 0 |
| `zwsp_inject` | 1.0 | 505 | 505 | 504 | 0 |

각 변형에서 변경이 504건인 이유는 적용 가능한 한글 음절이 없어 생성 단계부터 원문과 같았던 시드
1건이 포함됐기 때문이다. `chosung`, `tensify`, `break_spacing`은 이번 MVP의 비지원 범위이므로
정규화기가 변경하지 않았다.

이 결과는 문자열 정확 복원과 clean mutation 검증이다. 가드레일 탐지 복원 효과는 이후 E0/E1/E2/E3
평가에서 별도로 측정한다.

## 테스트

```powershell
python -m unittest discover -s tests -v
```

현재 테스트는 clean 무변경, 현대·호환 자모, 음절 경계, ZWSP, emoji ZWJ, 독립 초성, 문장부호,
코드스위칭, 원문 offset, 빈 입력과 결정성을 포함한다.
