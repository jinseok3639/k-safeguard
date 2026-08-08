# 초성체 bounded partial restoration 비교

> 실행일: 2026-08-08
>
> candidate generator: `0.4.0`
>
> 상태: `PROVISIONAL_DEV_ONLY / DEFAULT_OFF`

긴 완전 초성 span 전체를 사전 단어로 덮을 수 없을 때, 신뢰한 도메인 source와 일치하는 내부 구간
하나만 복원하고 나머지 초성은 보존하는 opt-in 탐색을 확인했다. 예를 들어
`ㄱㄱㅅㅅㅌㄴ`에서 `ㅅㅅㅌ`만 `시스템`으로 바꿔 `ㄱㄱ시스템ㄴ` 후보를 만들 수 있다.

## 안전 경계

- 완전 초성 span의 진부분 문자열만 대상으로 한다.
- 호출자가 `partial_sources`로 명시한 source만 검색하며 일반 `wordfreq` source에는 자동 적용하지 않는다.
- 기본 최소 근거는 초성 3개다.
- 한 후보에서 부분 복원은 기본 1회로 제한한다.
- 원문 view와 복원하지 않은 초성은 그대로 보존한다.
- replacement에 원문 offset, source, 복원 범위와 `partial=true`를 기록한다.
- Gateway와 `WordfreqChosungProvider` 모두 명시적으로 활성화해야 한다.

## 표준 후보 한도 비교

두 조건 모두 span당 3개, 문장당 원문 포함 16개 후보를 사용했다.

- control: [`chosung_segmented_v1.json`](./baselines/chosung_segmented_v1.json)
- partial: [`chosung_partial_v1.json`](./baselines/chosung_partial_v1.json)

| 조건 | 후보 생성 | 평균 최선 초성 복원 | 평균 후보 | 부분 후보 생성 행 | truncation | 성공 |
|---|---:|---:|---:|---:|---:|---:|
| segmentation control | 74.55% | 13.72% | 7.94 | 0 | 62.97% | 0 |
| + bounded partial | 74.55% | 13.72% | 7.94 | 1/1,010 | 62.97% | 0 |

부분 후보는 1개 행에서 3개가 최종 후보에 포함됐지만 oracle 초성 복원률, 후보 생성률, 실패 taxonomy와
truncation은 바뀌지 않았다.

## 넓은 후보 한도 진단

부분 후보가 기본 상한에 가려지는지 확인하기 위해 span당 16개, 문장당 64개로 넓혀 같은 비교를 했다.

- wide control: [`chosung_segmented_wide_v1.json`](./baselines/chosung_segmented_wide_v1.json)
- wide partial: [`chosung_partial_wide_v1.json`](./baselines/chosung_partial_wide_v1.json)

| 조건 | 평균 최선 초성 복원 | 평균 후보 | 부분 후보 생성 행 | 부분 후보 합계 | truncation |
|---|---:|---:|---:|---:|---:|
| wide control | 15.54% | 28.68 | 0 | 0 | 40.00% |
| wide partial | 15.54% | 28.70 | 3/1,010 | 34 | 40.10% |

후보 폭을 넓혀도 복원률은 개선되지 않았고 평균 후보와 truncation만 소폭 증가했다. 현재 초성 benchmark는
공백을 유지한 단일 기법 변형이어서, 부분 복원이 필요한 긴 미일치 span 자체가 거의 없기 때문이다.
탐색된 일부 `명령어` 일치는 원문의 다른 단어와 초성이 우연히 겹친 사례도 있어 정상 입력 오탐 위험을
배제할 수 없다.

## 판정

bounded partial restoration은 무의존·신뢰 source 한정 opt-in 실험 기능으로만 유지한다. 현재 데이터에서는
활성화 근거가 없으므로 기본 Gateway, `WordfreqChosungProvider`, 배포 권장 설정에는 연결하지 않는다.
초성체와 띄어쓰기 파괴가 결합된 별도 평가셋과 실제 가드레일의 `TPR`/`ΔFPR`을 함께 측정하기 전에는
방어 개선으로 주장하지 않는다.

이번 결과는 다음 개선에서 후보 생성 규칙을 더 늘리는 대신, 현재 후보 view가 실제 가드레일 탐지를
얼마나 복구하고 정상 입력 오탐을 얼마나 올리는지 먼저 측정해야 함을 보여준다.

## 재현

```powershell
python -m experiments.benchmark.run_chosung_lexical_diagnostic `
  --priority-lexicon experiments\benchmark\lexicons\guardrail_domain_v1.txt `
  --priority-source guardrail-domain-v1 `
  --expand-priority-particles `
  --allow-segmentation `
  --allow-partial-restoration `
  --output experiments\benchmark\baselines\chosung_partial_v1.json
```

넓은 한도 비교는 위 명령에 `--max-options-per-span 16 --max-candidates 64`를 추가한다.
