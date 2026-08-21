# 정규화 E0/E1/E2/E3 평가

`run_normalizer_evaluation.py`는 `hf_repo/benchmark.jsonl`을 Kanana Safeguard-Prompt에 입력해
정규화 gateway OFF/ON 효과를 동일 모델 설정으로 비교한다. 이 Prompt track은
[`EVALUATION_SPEC.md`](../../dev_note/EVALUATION_SPEC.md) 0.2.0의 주 평가다.

## 조건

| 입력 | Gateway OFF | Gateway ON |
|---|---|---|
| clean | E0 | E3 |
| obfuscated | E1 | E2 |

- E0/E3는 독립 시드마다 한 번 실행한다.
- E1/E2는 clean을 제외한 각 variant에 대해 실행한다.
- Prompt 모델, revision, chat template, dtype와 batch size는 네 조건에서 같다.
- E2/E3만 `k_safeguard.normalization.normalize_korean`을 적용한다.
- 원문부터 놓친 공격은 CER 분모에 포함하지 않는다.
- 생성 단계에서 실제로 바뀌지 않은 variant는 gateway 지표에서 제외한다.

## 실행

저장소 루트에서 로컬 모델 환경을 활성화한 뒤 실행한다.

```powershell
. .\experiments\guardrail\enter-env.ps1
python -m experiments.benchmark.run_normalizer_evaluation
```

몇 개의 독립 시드와 특정 기법만 확인할 때는 다음과 같이 실행한다. technique filter를 적용해도
paired baseline을 위해 해당 시드의 clean E0/E3는 함께 실행한다.

```powershell
python -m experiments.benchmark.run_normalizer_evaluation `
  --limit-seeds 3 `
  --technique jamo_decompose `
  --bootstrap-samples 100 `
  --run-id normalizer-eval-smoke
```

기본 bootstrap은 평가 규격에 따라 독립 `seed_id` cluster 10,000회다. 동일 run ID 결과는
덮어쓰지 않는다.

## 집계 지표

- CER와 Detection Retention
- NRR와 Residual CER
- Recovery Gain
- ΔFPR-clean, ΔFPR-obfuscated
- Clean Mutation Rate
- Exact Restoration
- normalizer·guardrail latency와 invalid/error rate

전체 결과 외에 family, technique, technique×intensity와 category별 결과를 기록한다. 전체·그룹
추정치는 먼저 같은 seed의 variant를 평균하고 seed를 같은 가중치로 평균한다. 행 단위 micro 값은
보조 지표로 함께 저장한다.

## 산출물

```text
results/<run_id>/
├── manifest.json
├── predictions.jsonl
├── summary.json
├── condition_summary.csv
├── report.md
└── errors.jsonl
```

`predictions.jsonl`에는 원문·변형문·정규화문이 포함되므로 `results/`는 Git에서 제외한다. manifest는
Git commit, dataset SHA-256, 모델 lock, tokenizer template hash, normalizer version과 bootstrap 설정을
고정한다.

집계 결과의 표·시각화·해석은 [`reports/normalizer_evaluation.ipynb`](../../reports/normalizer_evaluation.ipynb)에서
재현한다. 보고서 노트북은 `manifest.json`, `summary.json`, `condition_summary.csv`만 읽으며 원문이 있는
`predictions.jsonl`은 로드하지 않는다.

## 해석 제한

이 runner는 Prompt track의 가드레일 판정과 문자열 정확 복원을 측정한다. 실행·표본·모델 coverage가
규격의 유효성 게이트를 통과하면 가드레일 결과는 `VALID_GUARDRAIL_ONLY`로 기록할 수 있다. 하위 LLM
intent-recognition과 semantic fidelity를 아직 측정하지 않으므로 disparity·RBE·ASR 평가는
`INCOMPLETE`다.

공개 505개 시드는 이미 규칙 개발과 오류 분석에 사용된 `DEVELOPMENT_POPULATION`이므로 결과 지위는
최대 `DEVELOPMENT_EVIDENCE`다. 일반화된 회복을 주장하려면 별도로 봉인하고 사전등록한 locked test가
필요하다.
