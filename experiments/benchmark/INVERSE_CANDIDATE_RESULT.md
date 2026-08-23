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

## 재현

```powershell
$env:PYTHONPATH=(Resolve-Path .\src).Path
python -m experiments.benchmark.run_inverse_candidate_diagnostic
```

기계 판독 baseline은 [`baselines/inverse_candidate_v1.json`](./baselines/inverse_candidate_v1.json)에
고정했다.

## 남은 검증

- 독립 locked benign에서 provider 활성화율과 OR-policy ΔFPR 측정
- P3 후보의 Kanana 종단 간 NRR·호출 비용 측정
- O2 문맥 ranker의 cap 9 exact-hit 개선 여부 측정
