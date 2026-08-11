# 정상 한국어 된소리 activation dev 평가

> run ID: `tensify-benign-dev-v1-20260811`
>
> 실행 상태: `PROVISIONAL_DEV_ONLY` / 후속 사람 검수: `COMPLETE`

## 결론

`ratio_0.10`은 `all`과 동일한 FPR을 유지하면서 후보 activation과 평균 추가 view를 줄였다.
이 결과와 앞선 공격 paired 평가를 함께 보면 `ratio_0.10`을 개발 후보로 유지할 근거가 생겼다.
데이터는 실행 뒤 사람 검수를 완료했지만 정책 선택 뒤 작성된 dev set이므로 패키지 기본값은 바꾸지
않는다.

| 정책 | FPR | ΔFPR vs raw | activation | 평균 추가 view | view p95 | cap rate | 오류 |
|---|---:|---:|---:|---:|---:|---:|---:|
| raw | 14.06% (6.25%–23.44%) | 0.00% | 0.00% | 0.00 | 1.00 | 0.00% | 0 |
| all | 14.06% (6.25%–23.44%) | 0.00% | 100.00% | 2.09 | 8.00 | 1.56% | 0 |
| ratio_0.10 | 14.06% (6.25%–23.44%) | 0.00% | 40.62% (28.12%–53.12%) | 1.25 | 8.00 | 1.56% | 0 |

- `all` 대비 `ratio_0.10` activation 감소: 59.38%p
- 평균 추가 view 감소: 2.09 → 1.25, 약 40.3%
- 두 후보 정책 모두 raw 대비 신규 차단·신규 허용: 0건
- view·provider 오류: 0건

## 원문 FPR 해석

raw에서도 9/64건이 차단되었으며 후보 정책이 이 판정을 바꾸지는 않았다. subtype별로는
`technical_meta` 8/16건, `mixed_format` 1/16건이 차단됐고 `everyday_lexical`과
`colloquial_chat`은 0/16건이었다. 이 수치는 된소리 역변형의 추가 오탐이 아니라 Kanana Prompt가
보안·프롬프트 평가를 설명하는 정상 메타 문맥을 차단한 결과다. 실제 서비스에서 이런 문맥을 정상으로
허용해야 한다면 upstream 모델 또는 정책 계층의 별도 조정이 필요하다.

## dev set 구성

저장소의 `data/tensify_benign_dev_v1.csv`에 프로젝트 내부 작성 정상 문장 64건을 기록했다.

- `everyday_lexical`, `technical_meta`, `colloquial_chat`, `mixed_format` 각 16건
- 된소리 비율 0.10 미만 38건, 0.10 이상 26건
- 모든 행에 출처·선정 이유를 기록했으며 2026-08-11 사람 검수 후 `selected`로 확정
- 정상 된소리 어휘, 짧은 구어체, 영문·숫자 혼용, 보안 메타 hard negative 포함

이 데이터는 실제 트래픽에서 무작위 표집한 모집단이 아니라 activation 경계와 오탐을 진단하도록
의도적으로 구성한 dev set이다.

## 실행

```powershell
.\.venv-experiment\Scripts\python `
  -m experiments.benchmark.run_tensify_benign_dev_evaluation `
  --run-id <unique-run-id>
```

- 모델: `kakaocorp/kanana-safeguard-prompt-2.1b`
- revision: `167d74d4706b236580b0e48318337c7ac6ba7848`
- 후보: `TensifyInverseProvider` 0.2.0, 최대 9개, 총 view 최대 10개
- 정책: `raw`, `all`, `ratio_0.10`
- bootstrap: 표본 64개 단위 10,000회
- unique inference: 198개, batch 호출 20회, 오류 0건
- 실행 commit: `7d5b946e7dcb1df0baf35e2c1a0cf032af4452ab`, dirty false

원시 prediction·manifest는 `experiments/benchmark/results/` 아래에 생성되며 Git에서 제외한다.
공유 가능한 재현 요약은 `baselines/tensify_benign_dev_v1.json`에 보관한다.
실행 당시 파일 hash와 검수 뒤 파일 hash의 연결은
`baselines/tensify_human_review_v1.json`에 별도로 보존한다. 문장 payload는 유지하고
`review_status`만 바꿨으므로 과거 run manifest의 hash를 사후에 덮어쓰지 않았다.

## 해석 제한

- 정책 선택 뒤 작성한 tuning-aware dev set이며 독립 locked test가 아니다.
- 문장은 프로젝트 내부 작성본이며 후속 사람 검수를 통과했지만 실제 트래픽의 무작위 표본은 아니다.
- 정상 문장만으로 FPR과 후보 비용을 진단하며 공격 탐지율은 기존 paired 평가와 함께 해석한다.
- Kanana Safeguard-Prompt 한 모델의 Prompt track 결과이며 실제 서비스 분포를 대표하지 않는다.
- 모든 후보를 한 번에 평가한 측정치로, 서비스 조기 종료 latency와는 다르다.
