# 자모분해·ZWSP 모집단 정규화 결과

> run ID: `normalizer-eval-full-20260808`
>
> 결과 지위: 공개 505개 시드의 개발 모집단 근거

> **호환성 주의**: 이 실행은 겹받침을 단일 호환 자모로 생성하던 커밋 `3c1c004`의 스냅샷이다.
> 이후 생성기는 실제 키보드 입력처럼 겹받침을 두 낱자로 분해하도록 바뀌었다. 따라서 아래
> `jamo_decompose` 가드레일 수치는 역사적 근거이며, 최신 생성기 기준 현재 성능으로 사용하려면
> 다시 실행해야 한다. `zwsp_inject`는 이 생성기 변경의 영향을 받지 않았다.

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

다음 표는 Kanana 실행 당시 데이터 스냅샷의 결과다.

| technique | intensity | 전체 exact | 실제 변경 variant exact | 생성 오류 |
|---|---:|---:|---:|---:|
| `jamo_decompose` | 0.5 | 505/505 | 504/504 | 0 |
| `jamo_decompose` | 1.0 | 505/505 | 504/504 | 0 |
| `zwsp_inject` | 0.5 | 505/505 | 504/504 | 0 |
| `zwsp_inject` | 1.0 | 505/505 | 504/504 | 0 |

적용 가능한 한글 음절이 없는 공격 시드 1개는 생성 단계부터 원문과 같았다. `505/505`는 문자열
동일성 지표이며 가드레일 차단 건수가 아니다.

현재 겹받침 낱자형 생성기로 다시 만든 벤치마크에서 `jamo_decompose` exact restoration은 intensity
0.5에서 463/505, 1.0에서 425/505다. 최신 문자열 결과는
[`dev_note/NORMALIZER.md`](../../dev_note/NORMALIZER.md)에 기록하며, 아래 E1/E2 스냅샷과 섞지 않는다.

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
[`normalization.text not in seen`](https://github.com/jinseok3639/k-safeguard/blob/main/src/k_safeguard/gateway.py#L102-L114)
조건 때문에 정규화 결과가 원문과 같으면 중복 view를 추가하지 않는다. 따라서 **정규화 무변경 입력**에서는
classifier 호출 수와 판정이 구조적으로 그대로다. 이 보장은 모든 가능한 정상문이 무변경이라는 뜻은 아니다.
별도의 benign hard-negative와 손실성 provider 평가는 계속 필요하다.

난독화 benign에서 E1→E2 ΔFPR은 `jamo_decompose` +0.49%p, `zwsp_inject` +0.25%p였다. 두 값의
seed-cluster bootstrap 95% CI는 각각 -2.21%p~+3.19%p, -1.96%p~+2.45%p로 0을 포함한다.

## 해석 제한

- 측정 대상은 Prompt track 가드레일 판정이다. 하위 LLM intent-recognition·semantic fidelity와 실제
  공격 성공률은 측정하지 않았다.
- 문자열 exact restoration, NRR, 순 Recovery Gain은 서로 다른 질문에 답하므로 한 수치처럼 합치지
  않는다.
- 독립 locked test 전에는 일반적인 “방어력 복원”을 주장하지 않는다.
- `jamo_decompose`는 최신 겹받침 낱자형 생성기로 E1/E2를 재실행하기 전까지 역사적 비교로만 쓴다.
