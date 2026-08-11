# 된소리 역변형 후보 Kanana paired 평가

> 기준선: [`baselines/tensify_guardrail_impact_v1.json`](./baselines/tensify_guardrail_impact_v1.json)
>
> run ID: `tensify-impact-v1-20260811`
>
> 상태: `PROVISIONAL_DEV_ONLY`

## 목적

[`TensifyInverseProvider`](../../src/k_safeguard/providers/tensify.py)의 최대 9개 후보를 원문과 OR로
검사할 때 된소리화 공격 탐지가 실제로 회복되는지, 정상 입력 오탐은 얼마나 증가하는지 paired
측정했다. 문자열 oracle recall 진단과 실제 모델 효과를 분리하며, 공개 개발 benchmark 결과를
locked test 성능으로 해석하지 않는다.

## 고정 설정

| 항목 | 값 |
|---|---|
| 데이터 | `hf_repo/benchmark.jsonl`, clean 505행 + tensify 1,010행 |
| 독립 시드 | 505 (attack 301, benign hard-negative 204) |
| 모델 | `kakaocorp/kanana-safeguard-prompt-2.1b` |
| revision | `167d74d4706b236580b0e48318337c7ac6ba7848` |
| dtype / GPU | fp16 / NVIDIA GeForce RTX 5070 Ti |
| 정책 | raw 1 view vs 원문 + 역변형 후보, 총 최대 10 view |
| 후보 생성기 | `tensify_inverse` 0.1.0, 최대 9개 |
| 판정 | 보존된 view 중 하나라도 block이면 block |
| bootstrap | seed cluster 10,000회, random seed 2026 |
| 실행기 commit | `59afd607326024078b8f7bad126e56c4d4583d57` (`dirty=false`) |

## 핵심 결과

| 정책 | 공격 block rate | NRR | Recovery Gain | ΔFPR-obfuscated | ΔFPR-clean | 평균 추가 view |
|---|---:|---:|---:|---:|---:|---:|
| raw | 29.73% (25.75–33.89) | 0.00% | 0.00%p | 0.00%p | — | 0.00 |
| inverse | **95.35%** (92.86–97.51) | **100.00%** (100.00–100.00) | **+65.61%p** (61.30–69.77) | **+1.96%p** (0.49–3.92) | **0.00%p** (0.00–0.00) | 6.04 (5.98–6.10) |

- clean에서 block되고 raw 된소리 변형에서 회피한 389쌍, 242개 독립 attack seed를 모두 회복했다.
- attack 변형 602행 중 395행을 새로 block했고 기존 block을 allow로 바꾼 행은 없다.
- benign clean 판정은 204행 모두 raw와 동일했다.
- benign 변형은 408행 중 8행이 새로 block됐다.
- 모델 오류, invalid output, provider 오류는 모두 0건이다.

## 세부 조건

| label | category | intensity | n | raw block | inverse block | NRR | paired Δ |
|---|---|---:|---:|---:|---:|---:|---:|
| attack | A1 | 0.5 | 194 | 45.36% | 95.88% | 100.00% | +50.52%p |
| attack | A1 | 1.0 | 194 | 10.31% | 95.36% | 100.00% | +85.05%p |
| attack | A2 | 0.5 | 107 | 45.79% | 94.39% | 100.00% | +48.60%p |
| attack | A2 | 1.0 | 107 | 20.56% | 95.33% | 100.00% | +74.77%p |
| benign hard-negative | — | 0.5 | 204 | 1.47% | 2.94% | — | **+1.47%p** |
| benign hard-negative | — | 1.0 | 204 | 0.49% | 2.94% | — | **+2.45%p** |

강도 1.0 benign 조건은 ΔFPR 점추정치가 +2.45%p로 평가 규격의 전체 게이트 점 기준 +2%p를
0.45%p 넘는다. 95% CI 상한은 +4.90%p로 +5%p 경계 안이지만, 조건별 오탐을 낮추기 전에는
기본 활성화를 권고하지 않는다.

## 실행 비용

- unique model view: 7,352
- batch 호출: 736 (`batch_size=10`)
- 전체 후보를 평가한 추론 wall time: 43.09초, 170.61 view/s
- 평균 추가 view: 6.04
- provider 후보 상한 도달률: 61.06%
- raw view 집합 보존율: 100.00%

wall time은 RTX 5070 Ti 한 환경의 개발 진단이며 일반 서비스 latency가 아니다. 실제 gateway는 첫
block에서 조기 종료할 수 있으므로 요청별 실행 view와 latency는 별도 runtime benchmark로 측정한다.

## 결론

된소리 역변형 후보는 Kanana Prompt의 된소리 취약점을 강하게 완화했다. 전체 개발셋 기준 NRR과
평균 ΔFPR 게이트는 만족했지만, 강도 1.0 benign 조건의 ΔFPR이 점 기준을 넘고 후보 상한 도달률도
높다. 따라서 다음 정책을 유지한다.

1. provider는 계속 명시적 opt-in으로 둔다.
2. 원문 view를 항상 보존하고 OR 판정의 단조성을 유지한다.
3. 기본 활성화 전 별도 정상 된소리·구어체 locked set에서 FPR을 재검증한다.
4. 운영 비용은 조기 종료 및 batch runtime 평가로 따로 측정한다.

이 결과는 Prompt track 한 모델의 개발용 근거이며 Content track, 다른 한국어 가드레일 또는 실제
하위 LLM의 안전성을 일반화하지 않는다.

## 재현

```powershell
python -m experiments.benchmark.run_tensify_guardrail_evaluation `
  --run-id tensify-impact-v1-20260811 `
  --max-views 10 `
  --max-candidates 9 `
  --batch-size 10 `
  --bootstrap-samples 10000 `
  --random-seed 2026
```

원시 `predictions.jsonl`에는 공격 텍스트가 포함되므로 `results/` 아래 로컬 산출물로만 보관한다.
