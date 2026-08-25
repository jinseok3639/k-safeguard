# 된소리 역변형 후보 진단

> 기준선: [`baselines/tensify_inverse_v1.json`](./baselines/tensify_inverse_v1.json)
>
> historical baseline generator: `tensify_inverse` 0.1.0
>
> current provider: `tensify_inverse` 0.3.0

이 문서의 최초 oracle 기준선은 0.1.0으로 생성했다. provider 0.2.0은 후보 문자열·순서를
유지하면서 `min_tense_syllables`와 `min_tense_ratio` activation 조건을 opt-in으로 추가했다.
현재 0.3.0은 경음 음절이 17개 이상인 긴 입력의 후보 순서만 다양화한다.

## 목적

전체 정규화 평가에서 `tensify` 강도 1.0 공격의 raw block rate가 A1 10.31%, A2 20.56%로
가장 낮았다. 평음 초성을 경음 초성으로 바꾼 입력을 원문 하나로 확정하는 것은 불가능하므로,
기본 무손실 정규화기는 유지하고 원문과 함께 검사할 bounded 후보 provider를 진단했다.

## 후보 정책

- 완성형 한글의 `ㄲ·ㄸ·ㅃ·ㅆ·ㅉ` 초성을 `ㄱ·ㄷ·ㅂ·ㅅ·ㅈ`으로 되돌린다.
- 첫 후보는 모든 위치를 복원한 문자열이다.
- 경음 음절이 17개 미만이면 기존처럼 복원 위치가 많은 조합부터 생성한다.
- 17개 이상이면 복원 개수 `1, n-1, 2, n-2, ...` tier를 round-robin한다. 같은 개수에서는
  왼쪽 위치 조합부터 결정론적으로 생성한다.
- 후보는 최대 9개다. 기본 `Gateway(max_views=10)`에서 원문 1개와 함께 사용할 수 있다.
- 원문은 항상 보존하며 모든 후보를 `lossy=True`, `confidence=None`으로 표시한다.
- 외부 사전, 형태소 분석기, Torch와 모델 가중치가 필요 없다.

provider 0.2.0부터 다음 조건을 선택적으로 설정할 수 있다.

```python
TensifyInverseProvider(
    max_candidates=9,
    min_tense_syllables=1,
    min_tense_ratio=0.10,
    diversify_from=17,
)
```

기본값은 기존 동작과 같은 `min_tense_syllables=1`, `min_tense_ratio=0.0`이다. 개발셋 sweep에서는
`min_tense_ratio=0.10`이 NRR과 ΔFPR을 유지하면서 clean benign 후보 활성화를 55.39%에서 11.27%로
줄였다. 이는 아직 기본값이 아니라 별도 정상 구어체 dev set에서 검증할 후보이며, 자세한 비교는
[`TENSIFY_ACTIVATION_SWEEP.md`](./TENSIFY_ACTIVATION_SWEEP.md)에 있다.

## 재현 방법

```powershell
python -m experiments.benchmark.run_tensify_candidate_diagnostic `
  --input hf_repo\benchmark.jsonl `
  --max-candidates 9 `
  --diversify-from 17 `
  --output build\tensify_inverse_v3.json
```

입력은 clean 505행과 tensify 1,010행이다. `changed exact hit`는 실제로 문자열이 바뀐 변형만을
분모로 삼고, 최대 9개 후보 중 원문과 정확히 같은 문자열이 있는지를 측정한다.

## 결과

| label | intensity | n (변경) | changed exact hit | top-1 exact | 평균 후보 | truncation |
|---|---:|---:|---:|---:|---:|---:|
| attack | 0.5 | 301 (300) | 95.33% | 61.13% | 8.47 | 88.70% |
| attack | 1.0 | 301 (300) | 91.00% | 61.13% | 8.95 | 99.34% |
| benign | 0.5 | 204 (204) | 95.59% | 44.61% | 8.46 | 75.98% |
| benign | 1.0 | 204 (204) | 83.82% | 44.61% | 9.00 | 100.00% |
| **전체 tensify** | — | **1,010 (1,008)** | **91.77%** | **54.46%** | **8.72** | **91.58%** |

clean 입력에서도 경음 초성이 있으면 후보가 생긴다.

| clean label | n | 후보 생성률 | 평균 후보 | 평균 경음 음절 |
|---|---:|---:|---:|---:|
| attack | 301 | 38.54% | 0.52 | 0.45 |
| benign hard-negative | 204 | 55.39% | 0.92 | 0.72 |

## 해석과 결정

- 9-view 후보 집합은 변형 문자열의 91.77%에서 원문을 포함하므로 실제 가드레일 회복을 시험할
  충분한 oracle recall을 확보했다.
- top-1만 쓰면 exact hit가 54.46%에 그쳐 단일 전역 역변형으로 줄이지 않는다.
- 정상 benign 입력의 55.39%에서도 후보가 생기므로 OR 판정 시 FPR이 상승할 가능성이 있다.
  문자열 exact hit만으로 방어 효과나 기본 활성화를 주장할 수 없다.
- 현재 provider는 opt-in으로 유지한다. 동일 Kanana 설정의 후속 paired 평가는 완료했으며,
  NRR 100.00%, `ΔFPR-obfuscated` +1.96%p, `ΔFPR-clean` 0.00%p를 확인했다.
  세부 결과와 고강도 benign 조건의 한계는
  [`TENSIFY_GUARDRAIL_IMPACT.md`](./TENSIFY_GUARDRAIL_IMPACT.md)를 참고한다.

이 결과는 후보 생성 recall 진단이며 의미 보존이나 실제 모델 판정 결과가 아니다.

## 0.3.0 긴 입력 후보 순서 비교

0.2.0의 내림차순 조합 열거는 경음 음절 17개·후보 9개 입력에서 복원 개수가
`17, 16, 16, 16, 16, 16, 16, 16, 16`으로 몰렸다. 0.3.0은 같은 예산에서
`17, 1, 16, 2, 15, 3, 14, 4, 13`을 생성한다.

| 정책 | changed exact hit | top-1 exact |
|---|---:|---:|
| 0.2.0 기존 순서 | 925/1,008 (91.77%) | 549/1,008 (54.46%) |
| 0.3.0, `diversify_from=17` | 922/1,008 (91.47%) | 549/1,008 (54.46%) |

oracle exact hit는 3건 감소했지만, 저장된 Kanana 판정에 새 후보 133개만 추가 추론한 비교에서는
공격 block 574/602, benign block 12/408, NRR 389/389로 기존 정책과 같았다. 따라서 전체 복원
후보를 첫 순위에 유지하고, 실제로 조합 편향이 큰 17개 이상 입력만 다양화한다. 비교값은
[`baselines/tensify_candidate_order_v1.json`](./baselines/tensify_candidate_order_v1.json)에 고정했다.

이 비교는 공개 개발셋 결과다. 0.2.0으로 수행한 locked-test v2를 0.3.0의 독립 검증으로 재사용하지
않는다. 또한 lightweight provider에 언어 모델 의존성을 추가하지 않는다. 추후 음절·문맥 기반 후보
scorer를 검토하더라도 별도 데이터 분리와 독립 검증을 통과한 opt-in 계층으로 다룬다.
