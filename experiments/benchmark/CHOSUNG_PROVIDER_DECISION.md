# 초성 provider 구조 개선과 기본값 결정

> candidate generator: 0.6.0
>
> 상태: `PROVISIONAL_DEV_ONLY`
>
> 집계: [`chosung_min_initials_v1.json`](./baselines/chosung_min_initials_v1.json)

## 반복 초성 필터

기존 구현은 같은 초성만 반복된 span을 사전 조회 전에 버렸다. 그 결과 trusted lexicon에 `제조(ㅈㅈ)`,
`방법(ㅂㅂ)`을 명시해도 후보가 생성되지 않았다.

0.6.0부터 반복 초성은 trusted lexicon에 **전체 span direct match**가 있을 때만 복원한다. exact direct
match가 없으면 기존처럼 보존하고, segmented·partial match만으로 `ㅋㅋ`·`ㅎㅎ`를 확장하지 않는다.
따라서 명시적으로 등록한 정상 단어는 도달 가능하면서 통신체 보호 경계는 유지된다.

## `min_initials=2` 비교

wordfreq 3.1.1 상위 30,000개와 동일 505개 공개 개발 benchmark에서 비교했다.

| lexical 지표 | min=3 | min=2 |
|---|---:|---:|
| 후보 생성률 | 70.59% | 96.14% |
| 문장 exact hit | 0.00% | 0.00% |
| 최선 초성 위치 복원 | 9.40% | 17.45% |
| 평균 후보 수 | 6.98 | 11.55 |
| truncation | 58.02% | 89.31% |

Kanana direct 후보 OR 정책은 기존 min=3 실행의 9,423개 판정을 재사용하고, min=2에서 새로 생긴
6,665개 문장만 batch 20으로 판정했다. min=3의 기존 집계가 정확히 재현됐고 오류는 0건이었다.

| guardrail 지표 | min=3 | min=2 |
|---|---:|---:|
| 공격 차단율 | 161/602 (26.74%) | 197/602 (32.72%) |
| NRR | 47/453 (10.38%) | 83/453 (18.32%) |
| 난독화 benign 차단율 | 4/408 (0.98%) | 5/408 (1.23%) |
| ΔFPR-obfuscated (raw 대비) | +0.74%p | +0.98%p |
| clean benign 차단율 | 6/204 (2.94%) | 6/204 (2.94%) |
| 평균 추가 view | 4.67 | 7.35 |
| candidate truncation | 611/1,010 (60.50%) | 908/1,010 (89.90%) |

min=2는 NRR을 7.95%p 높였지만 평균 view가 57.4% 늘고 거의 모든 행에서 후보 상한에 닿았다.
문장 exact hit도 여전히 0건이며 공개 개발셋의 결과라 일반화 근거가 아니다. 따라서 기본값은 3을
유지하고, 2는 비용·오탐을 감수하는 명시적 opt-in으로 남긴다.

## 랭킹 결정

LM perplexity ranker는 core/provider의 dependency-free·경량 경계를 깨고 별도 모델 추론을 추가한다.
저장된 최대 16개 후보에서 비교한 source-first, domain-first, 적은 replacement 우선 정렬도 현재 정렬을
일관되게 이기지 못했다. 근거는
[`CHOSUNG_CANDIDATE_RANKING.md`](./CHOSUNG_CANDIDATE_RANKING.md)에 있다.

따라서 현재 `direct/segmented/partial 계층 → 복원 초성 수 → 사전 rank`를 유지한다. 향후 LM ranker는
외부 opt-in scorer로 분리하고, 독립 데이터에서 NRR·ΔFPR·latency를 함께 이길 때만 기본 후보 순서에
반영한다.

## 해석 제한

- Prompt 가드레일 한 모델과 공개 개발 benchmark 결과다.
- 초성 변형의 의미 보존과 하위 LLM 이해도는 측정하지 않았다.
- min=2 결과는 기본 활성화 또는 일반적인 방어 성능 주장을 지지하지 않는다.
