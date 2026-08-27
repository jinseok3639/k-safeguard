# 한국어 정규화기 MVP

`k_safeguard.normalization`은 기존 가드레일 앞단에서 정보 손실 없이 확정할 수 있는 한국어 표기 변형만
정규화하는 첫 번째 MVP다. 복원 모델을 사용하지 않으며, 모호한 입력은 원문을 유지한다.

## 지원 범위

| rule ID | 처리 대상 | 정책 |
|---|---|---|
| `remove_hangul_zwsp` | 한글·자모와 인접한 U+200B ZERO WIDTH SPACE | U+200B만 제거 |
| `normalize_halfwidth_hangul` | U+FFA1–U+FFDC의 현대 반각 한글 자모 | 표준 호환 자모로 변환 후 음절 조합 |
| `compose_modern_jamo` | `안` 같은 현대 조합형 자모열 | 명확한 초성+중성(+종성)을 음절로 조합 |
| `compose_compat_jamo` | `ㅇㅏㄴ`, `ㄱㅏㅂㅅ` 같은 호환 자모열 | 겹받침 낱자형과 다음 모음 경계를 확인해 음절로 조합 |

전역 Unicode NFC/NFKC를 적용하지 않고 지원 범위의 한글 자모열만 직접 조합한다. 반각 한글
filler(U+FFA0), 반각 가타카나와 전각 라틴 등은 보존하므로 한글과 무관한 결합문자, emoji ZWJ
sequence와 코드스위칭 입력을 임의로 바꾸지 않는다.

다음 항목은 문맥 없이는 원문을 확정할 수 없어 MVP에서 변경하지 않는다.

- 초성체
- 된소리·쌍자음화
- 연음·구개음화
- 띄어쓰기 파괴
- 일반 영문·숫자 사이의 zero-width 문자
- U+200C ZWNJ, U+200D ZWJ, U+2060 WORD JOINER, U+FEFF BOM, U+00AD SOFT HYPHEN
  (한글·자모 사이에 있어도 원문 그대로 보존)

초성체·된소리의 다중 후보 provider는 복원율과 오탐 평가 결과를 근거로 공개 API에서 제거했다.
기존 후보 생성 구현과 결과 문서는 과거 실험 재현용으로만 보존한다. 배포 `Gateway`와
`normalize_korean()`은 두 변형을 바꾸거나 여러 복원 view로 확장하지 않는다.

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

2026-08-21에 겹받침 낱자형을 포함해 재생성한 `hf_repo/benchmark.jsonl`
5,555행 전체를 실행했다.

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

[#45](https://github.com/jinseok3639/k-safeguard/issues/45)에서 `ㅄ` 같은 겹받침을
`ㅂ`+`ㅅ` 낱자로 분해하도록 생성기를 바로잡자 실패 122행(강도 0.5에서 42행,
1.0에서 80행)이 새로 드러났다. 단일 겹받침 코드포인트만 생성하던 이전 벤치마크의
`505/505`는 실제 키보드형 입력 커버리지를 과대평가했다. 이후
[#44](https://github.com/jinseok3639/k-safeguard/issues/44)에서 겹받침 11종의 낱자형과
다음 음절 모음 경계를 조합하도록 수정해 새 벤치마크에서도 `505/505`를 회복했다.

이 결과는 문자열 정확 복원과 clean mutation 검증이다. 가드레일 탐지 복원 효과는 이후 E0/E1/E2/E3
평가에서 별도로 측정한다.

## 테스트

```powershell
python -m unittest discover -s tests -v
```

현재 테스트는 clean 무변경, 현대·호환 자모, 반각 현대 한글 51개 매핑 전수, 대표 반각 음절과
음절 경계, 한글 인접 ZWSP 제거, ZWSP 외 format 문자 보존, emoji ZWJ, 독립 초성, 문장부호,
코드스위칭, 원문 offset, 빈 입력과 결정성을 포함한다. 현대 한글 11,172음절 반각 변환 전수 복원은
별도 진단에서 실패 0건을 확인했다.
