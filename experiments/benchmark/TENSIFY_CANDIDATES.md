# 된소리 역변형 후보 진단

> 기준선: [`baselines/tensify_inverse_v1.json`](./baselines/tensify_inverse_v1.json)
>
> candidate generator: `tensify_inverse` 0.1.0

## 목적

전체 정규화 평가에서 `tensify` 강도 1.0 공격의 raw block rate가 A1 10.31%, A2 20.56%로
가장 낮았다. 평음 초성을 경음 초성으로 바꾼 입력을 원문 하나로 확정하는 것은 불가능하므로,
기본 무손실 정규화기는 유지하고 원문과 함께 검사할 bounded 후보 provider를 진단했다.

## 후보 정책

- 완성형 한글의 `ㄲ·ㄸ·ㅃ·ㅆ·ㅉ` 초성을 `ㄱ·ㄷ·ㅂ·ㅅ·ㅈ`으로 되돌린다.
- 복원 위치가 많은 조합부터, 같은 개수에서는 왼쪽 위치 조합부터 결정론적으로 생성한다.
- 후보는 최대 9개다. 기본 `Gateway(max_views=10)`에서 원문 1개와 함께 사용할 수 있다.
- 원문은 항상 보존하며 모든 후보를 `lossy=True`, `confidence=None`으로 표시한다.
- 외부 사전, 형태소 분석기, Torch와 모델 가중치가 필요 없다.

## 재현 방법

```powershell
python -m experiments.benchmark.run_tensify_candidate_diagnostic `
  --input hf_repo\benchmark.jsonl `
  --max-candidates 9 `
  --output experiments\benchmark\baselines\tensify_inverse_v1.json
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
