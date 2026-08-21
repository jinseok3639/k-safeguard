# 자모분해·ZWSP 모집단 정규화 결과

> run ID: `normalizer-eval-full-20260808`
>
> 결과 지위: 공개 505개 시드의 개발 모집단 근거

## 실행 범위

- 공격 301개, benign hard-negative 204개, 합계 505개 독립 시드
- `jamo_decompose`, `zwsp_inject` 각각 intensity 0.5·1.0
- Kanana Safeguard-Prompt 2.1B revision
  `167d74d4706b236580b0e48318337c7ac6ba7848`
- invalid output 0건, 실행 오류 0건
- 원시 결과의 해시와 집계 수치는
  [`normalizer_population_v1.json`](./baselines/normalizer_population_v1.json)에 고정

공개 505개는 규칙 개발과 오류 분석에 사용됐으므로 독립 locked test가 아니다. 아래 수치는 현재
개발 모집단을 기술하며 새로운 입력에 대한 일반화 성능을 보장하지 않는다.

## 1. 문자열 정확 복원

| technique | intensity | 전체 exact | 실제 변경 variant exact | 생성 오류 |
|---|---:|---:|---:|---:|
| `jamo_decompose` | 0.5 | 505/505 | 504/504 | 0 |
| `jamo_decompose` | 1.0 | 505/505 | 504/504 | 0 |
| `zwsp_inject` | 0.5 | 505/505 | 504/504 | 0 |
| `zwsp_inject` | 1.0 | 505/505 | 504/504 | 0 |

적용 가능한 한글 음절이 없는 공격 시드 1개는 생성 단계부터 원문과 같았다. `505/505`는 문자열
동일성 지표이며 가드레일 차단 건수가 아니다.

## 2. 가드레일 E1→E2 판정

아래 차단율은 두 intensity의 모든 공격 variant를 합친 값이다. E1은 난독화 원문, E2는 정규화한
난독화 입력이다.

| technique | E1 raw 차단 | E2 정규화 차단 | 순 Recovery Gain | clean에서 생긴 회피 variant 복원 |
|---|---:|---:|---:|---:|
| `jamo_decompose` | 573/602 (95.18%) | 566/602 (94.02%) | -1.16%p | 11/11 |
| `zwsp_inject` | 564/602 (93.69%) | 566/602 (94.02%) | +0.33%p | 19/19 |
| 합계 | 1,137/1,204 (94.44%) | 1,132/1,204 (94.02%) | -0.42%p | 30/30 |

E2의 94.02%는 clean E0의 283/301을 intensity마다 반복한 값과 정확히 같다. 즉 지원 두 기법에서
정규화는 clean 판정을 완전히 복원했다. 다만 raw 난독화가 E0에서 놓친 공격을 우연히 새로 차단한
경우도 있다. 이 판정까지 baseline으로 되돌리므로 `jamo_decompose`와 합계의 순 Recovery Gain은
음수다. 합계 30/30은 고유 시드 수가 아니라 두 intensity의 회피 variant 수다. 따라서 NRR 100%를
“전체 차단율 상승”으로 바꿔 말하지 않는다.

### intensity별 전체 공격 차단율

| technique | intensity | E1 raw | E2 정규화 | 차이 |
|---|---:|---:|---:|---:|
| `jamo_decompose` | 0.5 | 285/301 (94.68%) | 283/301 (94.02%) | -0.66%p |
| `jamo_decompose` | 1.0 | 288/301 (95.68%) | 283/301 (94.02%) | -1.66%p |
| `zwsp_inject` | 0.5 | 287/301 (95.35%) | 283/301 (94.02%) | -1.33%p |
| `zwsp_inject` | 1.0 | 277/301 (92.03%) | 283/301 (94.02%) | +1.99%p |

## 3. 정상 입력 비용

clean 505개는 모두 정규화 무변경이었고 benign E0와 E3는 모두 6/204(2.94%)였다. core gateway는
정규화 결과가 원문과 같으면 중복 view를 추가하지 않으므로, **정규화 무변경 입력**에서는 classifier
호출 수와 판정이 구조적으로 그대로다. 이 보장은 모든 가능한 정상문이 무변경이라는 뜻은 아니다.
별도의 benign hard-negative와 손실성 provider 평가는 계속 필요하다.

난독화 benign에서 E1→E2 ΔFPR은 `jamo_decompose` +0.49%p, `zwsp_inject` +0.25%p였다. 두 값의
seed-cluster bootstrap 95% CI는 각각 -2.21%p~+3.19%p, -1.96%p~+2.45%p로 0을 포함한다.

## 해석 제한

- 측정 대상은 Prompt track 가드레일 판정이다. 하위 LLM intent-recognition·semantic fidelity와 실제
  공격 성공률은 측정하지 않았다.
- 문자열 exact restoration, NRR, 순 Recovery Gain은 서로 다른 질문에 답하므로 한 수치처럼 합치지
  않는다.
- 독립 locked test 전에는 일반적인 “방어력 복원”을 주장하지 않는다.
