# 초성 후보 view 가드레일 영향 평가

> 상태: `PROVISIONAL_DEV_ONLY`
>
> 기준선: [`baselines/chosung_guardrail_impact_v1.json`](./baselines/chosung_guardrail_impact_v1.json)
>
> 이 문서는 candidate generator 0.4.0 기준이다. 후보 집합 단조성을 보장한 0.5.0 재평가는
> [초성 후보 정책 단조성 개선](./CHOSUNG_CANDIDATE_MONOTONICITY.md)을 참고한다.

## 질문

초성 후보 생성기의 어휘 coverage가 낮더라도, 원문과 bounded 복원 후보를 가드레일에 함께 입력하면
실제 공격 차단율이 회복되는지 확인한다. 동시에 benign hard-negative의 오탐 증가와 후보 수 비용을
측정한다.

비교 정책은 다음과 같다.

| 정책 | 후보 구성 |
|---|---|
| `raw` | 무손실 정규화한 원문 1개 |
| `direct` | raw + 전체 span 직접 사전 일치 |
| `segmented` | direct + 최대 2개 단어 분할 복원 |
| `partial` | segmented + 신뢰 사전의 부분 복원 1회 |

모든 정책은 후보 중 하나라도 block이면 최종 block하는 OR 규칙을 사용한다. 후보 상한은 원문 포함
16개다.

## 실행 조건

- 데이터: `hf_repo/benchmark.jsonl`의 clean 505행과 chosung 1,010행
- 독립 시드: 505개(attack 301, benign 204)
- 모델: `kakaocorp/kanana-safeguard-prompt-2.1b`
- revision: `167d74d4706b236580b0e48318337c7ac6ba7848`
- 후보 사전: `guardrail-domain-v1` 조사 확장 + `wordfreq:ko` 상위 30,000개
- bootstrap: 시드 단위 10,000회, seed 2026
- 실행 오류: 0건 / 고유 모델 추론 14,785회

재현 명령은 저장소 루트에서 실행한다.

```powershell
.\.venv-experiment\Scripts\python `
  -m experiments.benchmark.run_chosung_guardrail_evaluation `
  --bootstrap-samples 10000 `
  --run-id <unique-run-id>
```

## 결과

괄호는 시드 단위 bootstrap 95% CI다. 공격 block rate와 ΔFPR-obf는 chosung 변형만 대상으로 한다.

| 정책 | 공격 block rate | NRR | Recovery Gain | ΔFPR-obf | ΔFPR-clean |
|---|---:|---:|---:|---:|---:|
| raw | 18.94% (15.95–21.93) | 0.00% | 0.00% | 0.00% | N/A |
| direct | 26.74% (23.09–30.56) | 11.96% (8.51–15.58) | +7.81%p (5.65–10.13) | +0.74%p (0.00–1.72) | 0.00%p |
| segmented | 27.91% (24.09–31.73) | 13.04% (9.60–16.67) | +8.97%p (6.64–11.46) | +0.49%p (0.00–1.23) | 0.00%p |
| partial | 27.91% (24.09–31.73) | 13.04% (9.60–16.67) | +8.97%p (6.64–11.46) | +0.49%p (0.00–1.23) | 0.00%p |

clean 기준 공격 block rate는 94.02%, benign block rate는 2.94%였고 후보 정책에서도 변하지 않았다.
segmented 정책의 residual evasion rate는 raw 80.04%에서 70.85%로 낮아졌다.

### 비용과 후보 상한

| 정책 | 변형당 평균 추가 view | 후보 상한 도달률 |
|---|---:|---:|
| raw | 0.00 | 0.00% |
| direct | 7.04 | 58.12% |
| segmented | 7.94 | 62.97% |
| partial | 7.94 | 62.97% |

정책별 레코드는 6,060개지만 같은 문자열의 추론 결과를 캐시해 실제 모델 호출은 14,785회로
제한했다. 서비스에서는 최악의 경우 원문 포함 16회 분류가 필요하므로 현재 형태를 기본 경로에 바로
연결하기에는 비용이 크다.

### 인접 정책의 paired 변화

`새 block`은 다음 정책이 추가로 막은 행, `새 allow`는 이전 정책이 막았지만 다음 정책이 놓친 행이다.

| 전환 | 공격 새 block / 새 allow | benign 새 block / 새 allow | 이전 후보 집합 보존율 |
|---|---:|---:|---:|
| raw → direct | 47 / 0 | 3 / 0 | 100.00% |
| direct → segmented | 10 / 3 | 0 / 1 | 57.33% |
| segmented → partial | 0 / 0 | 0 / 0 | 99.90% |

분할 후보를 더했는데 공격 3건이 새로 허용된 이유는 모델 판정의 역전이 아니라 후보 상한 경쟁이다.
segmented 후보 목록이 direct 후보의 완전한 상위 집합이 아니어서 일부 direct 후보가 밀려났다. 현재
bounded 후보 정책은 기능을 추가해도 판정이 단조롭게 강화된다고 가정할 수 없다.

## 판정

`EVALUATION_SPEC.md`의 locked-test 성공 기준 중 ΔFPR 조건은 만족하지만, 핵심 NRR 점추정치 50%
기준에는 크게 못 미친다. 또한 이 데이터는 개발 중 반복 사용한 공개 benchmark이므로 locked test가
아니다. 따라서 다음처럼 판정한다.

- 초성 후보 view가 공격 차단을 일부 회복한다는 개발용 근거는 확보했다.
- 일반적인 "방어력 복원" 또는 기본 활성화 근거로는 부족하다.
- partial restoration은 segmented 대비 판정을 한 건도 개선하지 못했으므로 계속 opt-in으로 둔다.
- 세 정책 모두 기본 Gateway에는 연결하지 않는다.

## 다음 개선 우선순위

1. direct 후보 슬롯을 먼저 예약해 segmentation이 기존 유효 후보를 밀어내지 않도록 단조성을 보장한다.
2. 후보 순위화 또는 사전 필터로 평균 view 수와 60%대 상한 도달률을 낮춘다.
3. 변경 후 같은 paired 전환 지표와 ΔFPR을 다시 측정한다.
4. 규칙 동결 뒤 별도의 사람 검수 locked test에서 최종 성공 기준을 판정한다.

## 해석 제한

- Kanana Safeguard-Prompt 한 모델의 Prompt track 결과다.
- 하위 LLM의 intent comprehension과 semantic fidelity는 측정하지 않았다.
- 초성+띄어쓰기 파괴가 결합된 별도 조건은 포함하지 않았다.
- 원문이 든 로컬 `results/`는 Git에서 제외하고, 집계 기준선만 커밋한다.
