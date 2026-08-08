# 초성체 사용자·도메인 사전 결합 비교

> 실행일: 2026-08-08
>
> candidate generator: `0.2.0`
>
> 상태: `PROVISIONAL_DEV_ONLY`

`chosung-error-v1` 기준선에서 가장 큰 병목으로 확인된 후보 recall을 개선하기 위해 사용자·도메인
사전을 일반 `wordfreq` 사전보다 먼저 검색하는 방식을 비교했다. 공개 benchmark 원문과 변형문에서는
단어를 추출하지 않았다.

## 구현 경계

- `ChosungLexicon.from_sources()`는 선언 순서대로 source 우선순위를 부여한다.
- 같은 단어가 여러 source에 있으면 가장 먼저 선언한 source만 보존한다.
- 각 replacement에 `lexicon_source`와 source 내부 rank를 기록한다.
- `expand_korean_noun_particles()`는 사용자 사전에만 선택적으로 적용한다.
- 기본 Gateway와 기존 단일 사전 API는 바뀌지 않으며 외부 dependency도 추가하지 않는다.
- `WordfreqChosungProvider`도 `priority_words`를 명시한 경우에만 결합 사전을 사용한다.

## 사전 출처

[`lexicons/guardrail_domain_v1.txt`](./lexicons/guardrail_domain_v1.txt)는 `EVALUATION_SPEC.md`의 A1/A2
범주와 프로젝트 공개 API 용어에서 정한 명사 50개다. 결과를 본 뒤 benchmark 정답 단어를 추가하지
않았다.

조사 확장은 완성형 한글 명사의 종성 여부에 따라 은/는, 이/가, 을/를, 과/와, 으로/로를 선택하고
의, 에, 에서, 도, 만을 추가한다. 50개 기본형에서 550개 variant가 생성되며 일반 빈도 사전에는 이
확장을 적용하지 않는다.

## 비교 조건

세 조건 모두 같은 1,010행, `wordfreq==3.1.1`, 단어 상한 30,000, span 후보 3개, 문장 후보 16개를
사용했다.

| 조건 | 인덱싱 단어 | 설명 | 결과 파일 |
|---|---:|---|---|
| control | 25,360 | `wordfreq:ko`만 사용 | [`chosung_wordfreq_v2.json`](./baselines/chosung_wordfreq_v2.json) |
| domain | 25,408 | 도메인 기본형 50개 우선 | [`chosung_domain_v1.json`](./baselines/chosung_domain_v1.json) |
| domain+particles | 25,908 | 도메인 기본형·조사형 550개 우선 | [`chosung_domain_particles_v1.json`](./baselines/chosung_domain_particles_v1.json) |

## 결과

| 조건 | 후보 생성 | 평균 최선 초성 복원 | 후보 미생성 | 과잉 복원 proxy | 정답 후보 누락 | 성공 | truncation |
|---|---:|---:|---:|---:|---:|---:|---:|
| control | 70.59% | 9.40% | 297 | 171 | 542 | 0 | 58.02% |
| domain | 71.09% | 9.85% | 292 | 171 | 547 | 0 | 58.12% |
| domain+particles | 71.19% | 10.32% | 291 | 169 | 550 | 0 | 58.12% |

최선 조건은 control 대비 후보 미생성을 6건 줄이고 평균 초성 위치 복원을 0.92%p 높였다. attack은
7.67%에서 8.53%, benign 합성 변형은 11.97%에서 12.96%로 올랐다. 과잉 복원 proxy와 truncation은
각각 2건 감소, 0.10%p 증가해 큰 악화는 관찰되지 않았다.

정답 후보 누락이 542건에서 550건으로 늘어난 것은 후보 미생성·전면 오복원 8건이 부분 복원 범주로
이동했기 때문이다. 그러나 문장 exact 성공은 여전히 0건이므로 이 변화만으로 gateway 방어 성능이
개선됐다고 주장할 수 없다.

## 판정과 다음 병목

다중 사전 API는 사용자 환경에서 필요한 도메인 우선순위와 추적성을 제공하므로 유지한다. 다만 50개
명사와 조사 확장만으로는 문장 단위 정답 후보를 만들지 못했으므로 기본 provider에는 자동 연결하지
않는다.

문맥 ranker는 정답 후보가 존재할 때만 평가할 수 있다. 다음 단계에서는 ranker보다 먼저 긴 초성 span을
어절·조사·부분어 후보로 분할해 정답 token coverage를 확보해야 한다. 이때 후보 수와 truncation이
폭발하지 않도록 beam 제한을 유지하고 같은 오류 taxonomy로 재측정한다.

## 재현

```powershell
python -m experiments.benchmark.run_chosung_lexical_diagnostic `
  --output experiments\benchmark\baselines\chosung_wordfreq_v2.json

python -m experiments.benchmark.run_chosung_lexical_diagnostic `
  --priority-lexicon experiments\benchmark\lexicons\guardrail_domain_v1.txt `
  --priority-source guardrail-domain-v1 `
  --expand-priority-particles `
  --output experiments\benchmark\baselines\chosung_domain_particles_v1.json
```

기준선 파일은 덮어쓰지 않으므로 재현 확인 시 새 출력 경로를 사용해 JSON을 비교한다.
