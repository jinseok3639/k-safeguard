# 실험 산출물 인덱스

이 문서는 `experiments/benchmark/`에 커밋된 실험 자료를 목적과 판정 상태별로 찾기 위한 색인이다.
기존 runner와 회귀 테스트가 경로를 직접 참조하므로 파일을 물리적으로 이동하지 않고, 문서·실행기·
기계 판독 baseline을 한 묶음으로 연결한다.

## 보관 경계

- `baselines/*.json`: 집계 수치와 provenance를 고정한 Git 추적 산출물
- `data/*`: 사전 고정하거나 사람이 검수한 실험 입력
- `*.md`: 결과 해석, 상태, 한계와 재현 절차
- `run_*.py`, `prepare_*.py`, `freeze_*.py`: 실행·고정 도구
- `results/`, `predictions.jsonl`: 공격 원문을 포함할 수 있는 비공개 실행 산출물. Git에 넣거나 이
  인덱스에서 개별 파일을 열거하지 않는다.

`PROVISIONAL_DEV_ONLY`는 개발 모집단 근거이며 독립 일반화 증거가 아니다. `DO_NOT_PROMOTE`는
승격 기준을 통과하지 못했다는 뜻이다. `PASS` smoke는 실행 계약만 검증하며 성능 추정에 사용하지
않는다.

## 현재 배포와 직접 연결되는 근거

| 묶음 | 상태와 용도 | 결과 문서 | baseline | runner |
|---|---|---|---|---|
| 무손실 정규화 | 공개 505시드 개발 모집단. 자모분해·ZWSP 문자열 복원과 Kanana 판정 분리 | [`NORMALIZER_POPULATION_RESULT.md`](./NORMALIZER_POPULATION_RESULT.md) | `normalizer_jamo_decomposed_v1.json`, `normalizer_population_v1.json` | `run_normalizer_evaluation.py` |
| 띄어 쓴 자모 | 공개 505시드 개발 근거. 한 어절 exact 504/504지만 공백 삭제가 lossy라 opt-in | [`SPACED_JAMO_RESULT.md`](./SPACED_JAMO_RESULT.md) | `spaced_jamo_v1.json` | `run_spaced_jamo_diagnostic.py` |
| ML 자모 슬롯 복원 | 문자열 진단은 `PROVISIONAL_DEV_ONLY`, Kanana 평가는 `DO_NOT_PROMOTE` | [`ML_RESTORE_CANDIDATES.md`](./ML_RESTORE_CANDIDATES.md), [`ML_RESTORE_GUARDRAIL_IMPACT.md`](./ML_RESTORE_GUARDRAIL_IMPACT.md) | `ml_restore_v1.json`, `ml_restore_guardrail_impact_v1.json` | `run_ml_restore_evaluation.py` |
| Gateway 연결 smoke | `PASS`. 선택된 fixture의 OR 집계·trace 계약만 검증 | [`GATEWAY_CONTRACT_SMOKE.md`](./GATEWAY_CONTRACT_SMOKE.md) | 결과 문서에 고정 | `run_gateway_contract_smoke.py` |
| Kanana batch | 판정 parity와 처리량 진단. 모집단 정확도 근거가 아님 | [`KANANA_BATCH_BENCHMARK.md`](./KANANA_BATCH_BENCHMARK.md) | 결과 문서에 고정 | `run_kanana_batch_benchmark.py` |

## 연구 재현 전용 묶음

### 된소리 다중 후보

2026-08-25 결정으로 공개 API에서 제거됐다. 구현과 자료는 기존 실험 재현을 위해 보존한다.

| 단계 | 대표 문서 | baseline·입력 접두사 | 최종 해석 |
|---|---|---|---|
| 후보·activation 개발 | `TENSIFY_CANDIDATES.md`, `TENSIFY_ACTIVATION_SWEEP.md`, `TENSIFY_BENIGN_DEV.md` | `tensify_inverse_*`, `tensify_activation_*`, `tensify_benign_*` | `PROVISIONAL_DEV_ONLY` |
| 오탐 분석·정책 결정 | `TENSIFY_FALSE_POSITIVES.md`, `TENSIFY_ACTIVATION_DECISION.md` | `tensify_false_positives_*`, `tensify_human_review_*` | 개발 결과만으로 승격하지 않음 |
| 독립 locked test | `TENSIFY_LOCKED_PROTOCOL.md`, `TENSIFY_LOCKED_RESULT.md` | `tensify_locked_*`, `data/tensify_locked_candidates_v1.csv` | `LOCKED_TEST_PRIMARY / DO_NOT_PROMOTE` |
| 교차 모델 | `TENSIFY_QWEN_*`, `TENSIFY_WOLF_*` | `tensify_qwen_*`, `tensify_wolf_*` | Qwen은 `LIMITED_BASELINE_COVERAGE`, Wolf는 `VALID_OOD_REPLICATION` |

### 초성체 다중 후보

2026-08-25 결정으로 공개 API에서 제거됐다. 모든 `CHOSUNG_*.md`, `chosung_*.json`,
`run_chosung_*.py`는 연구 재현 전용이다. 대부분 `PROVISIONAL_DEV_ONLY`이며,
`CHOSUNG_RUNTIME_SMOKE.md`의 `PASS`는 런타임 계약만 뜻한다.

## 초기·대체된 자료

`run_clean_baseline.py`와 관련 기록은 2026-08-05의 24시드 파일럿이다. 이후 505시드
E0/E1/E2/E3 평가가 대체했으므로 최신 성능 근거로 인용하지 않는다. 삭제하지 않는 이유는 초기
스키마와 실행 경로의 회귀 재현 때문이다.

## 새 실험을 추가할 때

1. 결과 문서 상단에 상태와 해석 제한을 명시한다.
2. 기계 판독 집계는 `baselines/<experiment>_vN.json`으로 고정한다.
3. 민감한 행 단위 출력은 `results/<run_id>/`에 두고 Git에 추가하지 않는다.
4. 결과 문서에서 입력·runner·baseline과 모델 revision 또는 source commit을 연결한다.
5. 이 인덱스의 해당 묶음에 링크를 추가하고, 대체된 자료는 삭제 대신 지위를 표시한다.

