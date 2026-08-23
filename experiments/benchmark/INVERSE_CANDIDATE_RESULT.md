# O2/P3 bounded 역후보 진단 결과

> source commit: `5875620b3b6f65547fe22296f1c4dbed7a733335`
>
> generator commit: `63bc98d`
>
> 결과 지위: 공개 505개 시드의 개발 모집단 근거

## 질문과 누출 통제

variant 문자열만 받은 규칙 후보 생성기가 원문을 후보 집합 안에 포함하는지 측정했다. `original`은 후보
생성이 끝난 뒤 exact-hit 비교에만 사용하며 생성·순위화에는 전달하지 않는다. 따라서 target leakage는
없지만, 이 수치는 의미 보존이나 가드레일 차단 회복을 뜻하지 않는다.

Gateway 기본 view 예산 10에서 원문 1개를 제외하면 후보는 최대 9개이므로 cap 9를 주 판단점으로 삼았다.

## 결과

| 변형 | 변경 variant | cap 1 | cap 3 | cap 9 | cap 32 |
|---|---:|---:|---:|---:|---:|
| O2 종성 삽입 | 1,008 | 0 (0%) | 0 (0%) | 1 (0.10%) | 10 (0.99%) |
| O2 종성 유사음 | 742 | 12 (1.62%) | 15 (2.02%) | 53 (7.14%) | 323 (43.53%) |
| P3 단순 연음 | 599 | 12 (2.00%) | 91 (15.19%) | 224 (37.40%) | 284 (47.41%) |

O2 종성 삽입은 표면상 원래 받침과 삽입 받침을 구분할 근거가 없고, 종성 유사음도 다대일 역매핑 때문에
작은 후보 예산에서 exact-hit이 낮다. 규칙 provider로 제품 코드에 넣지 않고 형태소·사전·ML 문맥 순위화
대상으로 보류한다.

P3는 같은 예산에서 상대적으로 높은 37.40%를 보여 `LiaisonInverseProvider`로 구현했다. 다만 자연어
정상문에도 열린 음절+자음 초성 패턴이 흔하므로 원문을 보존하는 opt-in lossy 후보이며 기본 Gateway에는
연결하지 않는다.

## Kanana paired 결과

문자열 후보 진단 뒤 같은 505시드 모집단과 고정 Kanana revision에서 원문+최대 9후보 OR 정책을
평가했다.

| 지표 | raw | P3 inverse |
|---|---:|---:|
| 공격 차단 | 545/602 (90.53%) | 569/602 (94.52%) |
| 새 회피 복원 NRR | - | 13/23 (variant 56.52%, seed-balanced 56.82%, CI 36.36%~77.27%) |
| 난독화 benign 차단 | 9/408 (2.21%) | 10/408 (2.45%), Δ +0.25%p (CI 0%~+0.74%p) |
| clean benign 차단 | 6/204 (2.94%) | 7/204 (3.43%), Δ +0.49%p (CI 0%~+1.47%p) |
| 평균 추가 view | 0 | 8.08 (CI 7.90~8.24) |
| 후보 truncation | 0 | 1,159/1,515 (76.50%) |

공격 recovery gain은 +3.99%p(CI +2.33%p~+5.81%p)였고 model/provider 오류는 0건이었다. 이득은
분명하지만 후보 비용과 정상문 판정 전환도 관찰됐으므로 기본 활성화 근거로 쓰지 않고 opt-in 상태를
유지한다. 기계 판독 결과는
[`baselines/liaison_guardrail_v1.json`](./baselines/liaison_guardrail_v1.json)에 고정했다.

## 재현

```powershell
$env:PYTHONPATH=(Resolve-Path .\src).Path
python -m experiments.benchmark.run_inverse_candidate_diagnostic
```

기계 판독 baseline은 [`baselines/inverse_candidate_v1.json`](./baselines/inverse_candidate_v1.json)에
고정했다.

## 남은 검증

- 독립 locked benign에서 provider 활성화율과 OR-policy ΔFPR 측정
- P3 독립 locked benign에서 관찰된 ΔFPR·비용 재검증
- O2 문맥 ranker의 cap 9 exact-hit 개선 여부 측정
