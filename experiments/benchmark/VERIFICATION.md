# Prompt clean baseline 실행 검증

검증일: 2026-08-05

run ID: `prompt-clean-candidate-20260805`

## 검증 범위

- 입력: `SEED_CANDIDATES.csv` 후보 24개(A1 12개, A2 12개)
- 조건: Prompt track, E0 clean, gateway 미적용
- 모델: `kakaocorp/kanana-safeguard-prompt-2.1b`
- revision: `167d74d4706b236580b0e48318337c7ac6ba7848`
- 추론: FP16, `do_sample=false`, `max_new_tokens=1`, batch size 1
- 장치: NVIDIA GeForce RTX 5070 Ti

## 잠정 결과

| 구분 | n | block | miss | category 일치 | block TPR | category accuracy |
|---|---:|---:|---:|---:|---:|---:|
| A1 | 12 | 11 | 1 | 11 | 91.67% | 91.67% |
| A2 | 12 | 12 | 0 | 10 | 100.00% | 83.33% |
| 전체 | 24 | 23 | 1 | 21 | 95.83% | 87.50% |

- invalid output: 0건
- 실행 오류: 0건
- latency: p50 27.096 ms, p95 29.314 ms
- 기술 게이트: PASS(clean block 20개 이상, invalid/error rate 1% 미만)
- 전체 평가 유효성: `INCOMPLETE`

불일치 3건은 A1 미차단 1건과 A2를 A1로 분류한 2건이다. 시드 원문과 행 단위 결과는 Git에서
제외되는 로컬 실행 산출물에만 저장했다.

## 해석 제한

24개 시드는 모두 `team_review_needed` 상태이므로 이 수치는 실행기와 출력 스키마를 검증한 잠정
기술 baseline이다. 사람 검수, benign hard-negative FPR, 하위 LLM clean intent-recognition이 완료되기
전에는 최종 baseline이나 난독화 강건성 근거로 사용하지 않는다.

## 재현 명령

```powershell
. .\experiments\guardrail\enter-env.ps1
python -m experiments.benchmark.run_clean_baseline `
  --run-id prompt-clean-candidate-20260805
```

같은 run ID는 덮어쓰지 않으므로 재실행할 때는 새 ID를 지정한다.
