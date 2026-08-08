# 평가 보고서

이 폴더에는 모델 추론과 분리된 재현 가능한 분석 보고서를 둔다. 노트북은
`experiments/benchmark/results/<run_id>/`의 집계 산출물만 읽으며, 공격 프롬프트 원문이 들어 있는
`predictions.jsonl`은 열거나 출력하지 않는다.

## 환경 준비

저장소 루트에서 보고서 전용 가상환경을 만든다.

```powershell
python -m venv .venv-report
.\.venv-report\Scripts\python -m pip install -r reports\requirements.txt
```

VS Code나 Jupyter에서 `.venv-report` 커널을 선택하고
`normalizer_evaluation.ipynb`를 실행한다. 다른 실행 결과를 분석하려면 첫 번째 설정 셀의 `RUN_ID`를
바꾸거나 `K_SAFEGUARD_REPORT_RUN` 환경 변수를 지정한다.

```powershell
$env:K_SAFEGUARD_REPORT_RUN = "normalizer-eval-smoke"
.\.venv-report\Scripts\jupyter-nbconvert `
  --execute --to notebook --inplace reports\normalizer_evaluation.ipynb
```

## 보고서 경계

- 입력: `manifest.json`, `summary.json`, `condition_summary.csv`
- 제외: `predictions.jsonl`, `errors.jsonl`의 원문
- 지표: seed-balanced 추정치와 독립 seed cluster bootstrap 95% CI
- 현재 범위: Prompt track만 포함하므로 최종 판정은 `NOT_EVALUATED`다.
