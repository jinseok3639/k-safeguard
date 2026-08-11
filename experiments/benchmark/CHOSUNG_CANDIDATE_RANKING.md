# 초성 후보 ranking 진단

> 상태: `PROVISIONAL_DEV_ONLY`
>
> 기준선: [`baselines/chosung_candidate_ranking_v1.json`](./baselines/chosung_candidate_ranking_v1.json)

## 질문

Gateway 총 view 예산을 10으로 낮춘 뒤에도 후보 순위를 개선하면 더 작은 예산에서 같은 방어율을 얻을
수 있는지 확인한다. 개발 label이나 모델 block 결과를 정렬 feature로 사용하지 않고, 배포 시점에도
계산 가능한 후보 metadata만 비교한다.

## 방법

candidate generator 0.5.0의 최대 16개 후보와 저장된 Kanana 판정을 결합했다. 1,010개 초성 변형의
후보 목록이 원 실행과 정확히 일치하는지 먼저 확인한 뒤 다음 정렬을 counterfactual 비교했다.

| strategy | 정렬 규칙 |
|---|---|
| `current` | direct·segmented·partial 계층 → 복원 초성 수 → 사전 rank |
| `source_first` | 계층 → source rank 합 → 복원 초성 수 → 사전 rank |
| `domain_first` | 계층 → 모든 replacement가 도메인 사전인지 → 기존 순위 |
| `few_replacements` | 계층 → replacement 수 → 복원 초성 수 → source/rank |

모든 대안은 계층 우선순위를 유지하므로 `direct ⊆ segmented ⊆ partial` 불변식을 깨지 않는다.

```powershell
.\.venv-experiment\Scripts\python `
  -m experiments.benchmark.run_chosung_candidate_ranking_diagnostic `
  --source-run experiments\benchmark\results\chosung-impact-monotonic-20260808
```

## 최초 유효 후보 위치

NRR 분모에 해당하는 453개 공격 변형 중 후보 view로 추가 회복한 행은 52개다. 순위는 원문을 제외한
candidate rank이며, rank 1은 전체 view의 두 번째 위치다.

| 최초 block 후보 rank | 회복 공격 수 |
|---:|---:|
| 1 | 39 |
| 2 | 4 |
| 3 | 3 |
| 4 | 2 |
| 7 | 3 |
| 9 | 1 |
| 회복 없음 | 401 |

- 전체 회복의 39/52(75.00%)가 첫 후보에서 발생했다.
- direct 후보가 47/52(90.38%), segmented 후보가 5/52(9.62%)를 처음 회복했다.
- raw에서 safe였던 benign 중 새 오탐은 후보 rank 1, 5, 8에서 각각 1건 발생했다.

## 대안 정렬 비교

표의 값은 해당 총 view 예산에서 회복한 공격 수이며 분모는 453개다.

| strategy | budget 2 | budget 4 | budget 6 | budget 8 | budget 10 | budget 16 |
|---|---:|---:|---:|---:|---:|---:|
| `current` | **39** | **46** | **48** | **51** | **52** | 52 |
| `source_first` | 38 | 44 | 47 | **51** | 51 | 52 |
| `domain_first` | 38 | 45 | **48** | **51** | **52** | 52 |
| `few_replacements` | 37 | 43 | 47 | 50 | 51 | 52 |

현재 순위는 budget 2~10의 모든 지점에서 단독 1위 또는 공동 1위였다. source 우선과 replacement 수
우선은 작은 예산의 회복을 낮췄고, `source_first`와 `few_replacements`는 budget 10에서도 현재보다
공격 1건을 더 놓쳤다. benign block rate도 대안이 더 낮다는 일관된 근거가 없었다.

## 판정

- 현재 `계층 → 복원량 → 사전 rank` 순서를 유지한다.
- 개발셋에 맞춘 가중치나 block 결과 기반 점수는 추가하지 않는다.
- Gateway 기본 총 view 예산 10도 유지한다.
- 다음 순위 변경은 별도 locked validation 또는 새로운 독립 데이터에서 현재 정렬을 이기는 사전등록된
  휴리스틱이 있을 때만 검토한다.

## 해석 제한

- 저장된 최대 16개 후보 집합 안에서 순서만 바꾼 counterfactual 분석이다.
- 공개 개발 benchmark와 Kanana Prompt 한 모델에 한정된다.
- 후보의 의미 충실도나 하위 LLM 이해도는 측정하지 않는다.
- 현재 정렬이 보편적으로 최적이라는 뜻이 아니라, 조사한 안전한 휴리스틱 중 교체 근거가 없다는 뜻이다.
