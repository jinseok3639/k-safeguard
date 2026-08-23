# 띄어 쓴 자모 provider 모집단 진단

> source commit: `4699d0d614389f87f567ea0e90633c8b64843944`
>
> 상태: 공개 505개 시드의 개발 근거

## 방법

각 문장에서 자모 4~64개로 분해되는 첫 한글 어절 하나를 골라 모든 낱자 사이에 ASCII 공백을 넣었다.
provider에는 변형문만 전달하고 원문은 후보 생성 뒤 exact 비교에만 사용했다. 기본 Gateway와
`SpacedJamoProvider()`를 같은 변형문에 각각 적용했다.

## 결과

| 지표 | 결과 |
|---|---:|
| 독립 시드 | 505 |
| 변형 가능한 시드 | 504 |
| provider 활성화 | 504/504 |
| exact 복원 | 504/504 (100%) |
| 기본 Gateway 문자열 변경 | 0/504 |
| clean 입력 provider 활성화 | 0/505 |

겹받침과 다음 음절 모음 경계를 포함한 실제 공개 문장 어절에서도 exact residual은 0이었다. 공백 삭제는
여전히 손실성이므로 이 결과를 근거로 기본 정규화에 넣지 않고 opt-in 후보로 유지한다.

## 재현

```powershell
$env:PYTHONPATH=(Resolve-Path .\src).Path
python -m experiments.benchmark.run_spaced_jamo_diagnostic
```

기계 판독 결과는 [`baselines/spaced_jamo_v1.json`](./baselines/spaced_jamo_v1.json)에 고정했다.

## 제한

- 문장마다 한 어절만 변형해, 여러 어절 전체가 낱자+공백으로 이어져 원래 단어 경계가 사라지는 경우는
  측정하지 않았다.
- clean 원문에는 분리 자모열이 없어 activation이 0인 것이며 별도 교육용 자모 hard-negative locked
  set 결과가 아니다.
- Kanana NRR·난독화 benign ΔFPR·하위 LLM 의미 이해는 별도 종단 간 평가가 필요하다.
