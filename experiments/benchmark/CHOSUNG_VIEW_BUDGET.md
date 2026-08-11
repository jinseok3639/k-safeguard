# 초성 후보 view budget 선택

> 상태: `PROVISIONAL_DEV_ONLY`
>
> 기준선: [`baselines/chosung_view_budget_v1.json`](./baselines/chosung_view_budget_v1.json)

## 목적

단조 후보 정책의 최대 16개 view는 현재 환경에서 변형당 평균 8.94회의 가드레일 판정을 요구했다.
pip gateway를 일반 환경에서 사용하려면 방어 지표를 유지하는 범위에서 기본 호출 예산을 줄여야 한다.

## 방법

candidate generator 0.5.0 전체 실행의 정렬된 후보 view를 앞에서부터 `1, 2, 4, 6, 8, 10, 12,
16`개만 남기고 OR 판정을 다시 집계했다. 모델을 다시 호출하거나 후보 순위를 바꾸지 않았다.

```powershell
.\.venv-experiment\Scripts\python `
  -m experiments.benchmark.run_chosung_view_budget_sweep `
  --source-run experiments\benchmark\results\chosung-impact-monotonic-20260808 `
  --budgets 1,2,4,6,8,10,12,16 `
  --bootstrap-samples 10000
```

추가로 `max_candidates=10`을 적용해 후보를 새로 생성한 결과가 16개 실행의 앞 10개와 6,060개
정책 레코드 모두에서 일치하는지 확인했다. 따라서 이번 prefix 재집계는 실제 10개 후보 생성 설정과
동일하다.

## 결과

segmented 정책 결과이며 괄호는 시드 단위 bootstrap 95% CI다. 평균 총 view에는 원문 1개가 포함된다.

| 총 view budget | 공격 block rate | NRR | ΔFPR-obf | 평균 총 view | 기록된 순차 지연 합 |
|---:|---:|---:|---:|---:|---:|
| 1 | 18.94% (15.95–21.93) | 0.00% | 0.00%p | 1.00 | 27.1ms |
| 2 | 25.58% (22.09–29.24) | 9.60% (6.70–12.68) | +0.25%p | 1.75 | 47.3ms |
| 4 | 26.74% (23.09–30.40) | 11.41% (8.15–14.86) | +0.25%p | 3.11 | 84.2ms |
| 6 | 27.08% (23.42–30.73) | 11.78% (8.51–15.22) | +0.49%p | 4.12 | 111.7ms |
| 8 | 27.57% (23.92–31.40) | 12.50% (9.06–16.12) | +0.49%p | 5.12 | 138.8ms |
| **10** | **27.74% (24.09–31.56)** | **12.86% (9.24–16.49)** | **+0.74%p** | **6.09** | **164.9ms** |
| 12 | 27.74% (24.09–31.56) | 12.86% (9.24–16.49) | +0.74%p | 7.05 | 191.1ms |
| 16 | 27.74% (24.09–31.56) | 12.86% (9.24–16.49) | +0.74%p | 8.94 | 242.1ms |

budget 8은 16 대비 공격 1건을 추가로 놓쳤다. budget 10부터 16까지 공격 block rate, NRR,
Recovery Gain, ΔFPR-clean/obfuscated와 인접 정책의 block/allow 전환이 모두 같았다.

## 선택

성능 점추정치를 16과 동일하게 유지하는 가장 작은 관측 예산인 **총 10 view**를 Gateway 기본값으로
선택한다.

- 평균 총 view: 8.94 → 6.09, 31.88% 감소
- 평균 추가 view: 7.94 → 5.09, 35.89% 감소
- 기록된 순차 모델 지연 합: 242.1ms → 164.9ms, 31.88% 감소
- 공격 block rate·NRR·ΔFPR 변화 없음
- `direct ⊆ segmented ⊆ partial` 단조성 유지

`Gateway(max_views=...)`로 서비스 예산을 명시적으로 재정의할 수 있다. lossy 초성 provider는 이번
변경 후에도 자동 활성화되지 않는다.

## 해석 제한

- 공개 개발 benchmark 한 개와 Kanana Prompt 모델 한 개의 결과다.
- 지연 합은 저장된 후보별 순차 추론 시간의 합이며 batching·동시성·네트워크를 포함한 서비스 p95가
  아니다.
- budget 10의 성능 동등성은 이 개발 데이터에서의 관측 결과이며 locked test 보장을 뜻하지 않는다.
- 낮은 예산은 후보 truncation을 늘리므로 후보 순위가 바뀌면 sweep을 다시 실행해야 한다.

현재 순위와 label-free 대안 휴리스틱 비교는
[초성 후보 ranking 진단](./CHOSUNG_CANDIDATE_RANKING.md)에 기록한다.
