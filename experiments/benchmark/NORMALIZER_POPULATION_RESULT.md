# 자모분해·ZWSP 모집단 정규화 결과

> 현재 자모분해 run ID: `normalizer-eval-jamo-decomposed-counts-20260823`
>
> ZWSP 고정 run ID: `normalizer-eval-full-20260808`
>
> 결과 지위: 공개 505개 시드의 개발 모집단 근거

> **호환성 주의**: `jamo_decompose`는 겹받침을 실제 키보드 입력처럼 두 낱자로 분해하는 커밋
> `a460f57`에서 다시 실행했다. `zwsp_inject`는 생성 방식이 바뀌지 않아 커밋 `3c1c004`의 고정
> 실행을 유지한다. 서로 다른 run의 수치를 합산하지 않는다.

## 실행 범위

- 공격 301개, benign hard-negative 204개, 합계 505개 독립 시드
- `jamo_decompose`, `zwsp_inject` 각각 intensity 0.5·1.0
- Kanana Safeguard-Prompt 2.1B revision
  `167d74d4706b236580b0e48318337c7ac6ba7848`
- 두 실행 모두 invalid output 0건, 실행 오류 0건
- 현재 자모분해 집계는
  [`normalizer_jamo_decomposed_v1.json`](./baselines/normalizer_jamo_decomposed_v1.json), 과거 결합 실행은
  [`normalizer_population_v1.json`](./baselines/normalizer_population_v1.json)에 고정

공개 505개는 규칙 개발과 오류 분석에 사용됐으므로 독립 locked test가 아니다. 아래 수치는 현재
개발 모집단을 기술하며 새로운 입력에 대한 일반화 성능을 보장하지 않는다.

## 1. 문자열 정확 복원

| technique | intensity | 전체 exact | 실제 변경 variant exact | 생성 오류 |
|---|---:|---:|---:|---:|
| `jamo_decompose` 낱자형 | 0.5 | 463/505 | 462/504 | 0 |
| `jamo_decompose` 낱자형 | 1.0 | 425/505 | 424/504 | 0 |
| `zwsp_inject` | 0.5 | 505/505 | 504/504 | 0 |
| `zwsp_inject` | 1.0 | 505/505 | 504/504 | 0 |

적용 가능한 한글 음절이 없는 공격 시드 1개는 생성 단계부터 원문과 같았다. `505/505`는 문자열
동일성 지표이며 가드레일 차단 건수가 아니다.

자모분해 두 강도의 실제 변경 variant를 합친 exact restoration은 886/1,008(87.90%, seed-cluster
bootstrap 95% CI 85.32%~90.48%)다. 문자열 exact와 아래 가드레일 판정은 별도 지표다.

## 2. 가드레일 E1→E2 판정

아래 차단율은 두 intensity의 모든 공격 variant를 합친 값이다. E1은 난독화 원문, E2는 정규화한
난독화 입력이다.

| technique | E1 raw 차단 | E2 정규화 차단 | 순 Recovery Gain | clean에서 생긴 회피 variant 복원 |
|---|---:|---:|---:|---:|
| `jamo_decompose` 낱자형 | 569/602 (94.52%) | 569/602 (94.52%) | 0.00%p | 14/15 |
| `zwsp_inject` | 564/602 (93.69%) | 566/602 (94.02%) | +0.33%p | 19/19 |

최신 자모분해의 순 차단율은 같지만, clean에서 차단됐던 공격이 난독화 후 새로 회피한 variant 15개 중
14개만 복원해 variant NRR 93.33%, seed-balanced NRR 92.31%(95% CI 76.92%~100%)였다. 문자열이 정확히
복원되지 않은 122개 중 가드레일 판정까지 복구되지 않은 residual은 1개다. 반대로 raw 난독화가 clean에서
놓친 공격을 우연히 차단할 수도 있으므로 순 차단율, NRR과 exact restoration은 방향이 다를 수 있다.

### intensity별 전체 공격 차단율

| technique | intensity | E1 raw | E2 정규화 | 차이 |
|---|---:|---:|---:|---:|
| `jamo_decompose` 낱자형 | 0.5 | 285/301 (94.68%) | 285/301 (94.68%) | 0.00%p |
| `jamo_decompose` 낱자형 | 1.0 | 284/301 (94.35%) | 284/301 (94.35%) | 0.00%p |
| `zwsp_inject` | 0.5 | 287/301 (95.35%) | 283/301 (94.02%) | -1.33%p |
| `zwsp_inject` | 1.0 | 277/301 (92.03%) | 283/301 (94.02%) | +1.99%p |

## 3. 정상 입력 비용

clean 505개는 모두 정규화 무변경이었고 benign E0와 E3는 모두 6/204(2.94%)였다. core gateway는
[`normalization.text not in seen`](https://github.com/jinseok3639/k-safeguard/blob/main/src/k_safeguard/gateway.py#L102-L114)
조건 때문에 정규화 결과가 원문과 같으면 중복 view를 추가하지 않는다. 따라서 **정규화 무변경 입력**에서는
classifier 호출 수와 판정이 구조적으로 그대로다. 이 보장은 모든 가능한 정상문이 무변경이라는 뜻은 아니다.
별도의 benign hard-negative와 손실성 provider 평가는 계속 필요하다.

난독화 benign에서 E1→E2 ΔFPR은 최신 `jamo_decompose` -0.25%p, `zwsp_inject` +0.25%p였다. 두 값의
seed-cluster bootstrap 95% CI는 각각 -2.45%p~+2.21%p, -1.96%p~+2.45%p로 0을 포함한다.

## 해석 제한

- 측정 대상은 Prompt track 가드레일 판정이다. 하위 LLM intent-recognition·semantic fidelity와 실제
  공격 성공률은 측정하지 않았다.
- 문자열 exact restoration, NRR, 순 Recovery Gain은 서로 다른 질문에 답하므로 한 수치처럼 합치지
  않는다.
- 독립 locked test 전에는 일반적인 “방어력 복원”을 주장하지 않는다.
- 최신 자모분해에서도 residual 1개가 남으므로 “완전 복원”이나 일반적인 차단율 향상을 주장하지 않는다.
