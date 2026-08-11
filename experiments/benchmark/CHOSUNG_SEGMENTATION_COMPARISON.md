# 초성체 span 분할 비교

> 실행일: 2026-08-08
>
> candidate generator: `0.3.0`
>
> 상태: `PROVISIONAL_DEV_ONLY`

사용자·도메인 사전과 조사 확장만으로 문장 exact 후보가 생기지 않아, 하나의 긴 완전 초성 span을 여러
사전 항목으로 분할하는 opt-in 탐색을 추가했다. 예를 들어 사전에 복합어 전체가 없어도
`ㅅㅅㅌㅍㄹㅍㅌ`을 `시스템 + 프롬프트`로 구성할 수 있다.

## 구현 경계

- 호환 초성만으로 이루어진 span에만 분할을 적용한다.
- 기본 설정은 최대 2 segment, segment당 빈도·source 우선 후보 1개다.
- span 전체를 사전 항목으로 덮을 수 있을 때만 분할 후보를 만든다.
- 직접 일치 후보와 분할 후보를 합친 뒤 기존 span당 3개, 문장당 16개 제한을 적용한다.
- 각 replacement에 segment 단어와 source를 기록한다.
- `allow_segmentation=False`가 기본이므로 기존 Gateway 결과는 바뀌지 않는다.

## 파라미터 선택

도메인 명사 50개와 조사 확장 550개를 우선 사전으로 사용하고 segment 수와 segment당 후보 수를
2×2로 비교했다.

| 최대 segment | segment 후보 | 평균 최선 초성 복원 | 평균 문장 후보 | truncation | 강도 1.0 truncation |
|---:|---:|---:|---:|---:|---:|
| 2 | 1 | 13.72% | 7.94 | 62.97% | 95.45% |
| 2 | 2 | 13.39% | 8.27 | 69.41% | 99.80% |
| 3 | 1 | 13.78% | 7.96 | 63.37% | 96.24% |
| 3 | 2 | 13.25% | 8.27 | 69.41% | 99.80% |

3×1의 복원이 0.06%p 높지만 탐색 깊이와 truncation도 늘어난다. 일반 CPU 환경과 gateway 지연을
우선해 2×1을 기본 opt-in 설정으로 선택했다. 후보 수를 늘렸을 때 oracle 복원까지 낮아지는 것은 틀린
빈도 후보가 문장 후보 상한을 먼저 차지하기 때문이다.

## 기준선 비교

세 조건은 모두 candidate generator 0.3.0으로 다시 실행했다.

- control: [`chosung_wordfreq_v3.json`](./baselines/chosung_wordfreq_v3.json)
- domain+particles: [`chosung_domain_particles_v2.json`](./baselines/chosung_domain_particles_v2.json)
- segmentation: [`chosung_segmented_v1.json`](./baselines/chosung_segmented_v1.json)

| 조건 | 후보 생성 | 평균 최선 초성 복원 | 평균 후보 | 후보 미생성 | 과잉 복원 proxy | 정답 후보 누락 | 성공 | truncation |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| wordfreq control | 70.59% | 9.40% | 6.98 | 297 | 171 | 542 | 0 | 58.02% |
| domain+particles | 71.19% | 10.32% | 7.04 | 291 | 169 | 550 | 0 | 58.12% |
| domain+particles+segment | 74.55% | 13.72% | 7.94 | 257 | 145 | 608 | 0 | 62.97% |

control 대비 후보 생성은 3.96%p, 평균 초성 위치 복원은 4.32%p 증가했다. 후보 미생성은 40건,
전면 오복원 proxy는 26건 감소했다. 평균 문장 후보는 0.96개, 전체 truncation은 4.95%p 증가했다.

강도 1.0의 평균 복원은 14.17%에서 21.37%로 증가했지만 truncation도 85.54%에서 95.45%로 올랐다.
강도 0.5의 truncation은 30.50%로 변하지 않았다. 분할이 완전 초성 어절에는 유효하지만 후보 상한에
가까운 입력에서는 추가 탐색 여유가 거의 없다는 뜻이다.

## 판정

span 분할은 무의존 opt-in 기능으로 유지할 만큼 부분 복원 개선이 확인됐다. 그러나 문장 exact 성공은
여전히 0건이며 `target_not_in_candidates`가 608건이다. 따라서 아직 문맥 ranker 학습·도입 단계가
아니다.

후속 bounded partial restoration 비교는
[`CHOSUNG_PARTIAL_RESTORATION_COMPARISON.md`](./CHOSUNG_PARTIAL_RESTORATION_COMPARISON.md)에 기록했다.
현재 공백 보존 초성 benchmark에서는 복원률 개선이 없어 기본 활성화 근거를 얻지 못했다.

## 재현

```powershell
python -m experiments.benchmark.run_chosung_lexical_diagnostic `
  --priority-lexicon experiments\benchmark\lexicons\guardrail_domain_v1.txt `
  --priority-source guardrail-domain-v1 `
  --expand-priority-particles `
  --allow-segmentation `
  --max-segments 2 `
  --max-options-per-segment 1 `
  --output experiments\benchmark\baselines\chosung_segmented_v1.json
```
