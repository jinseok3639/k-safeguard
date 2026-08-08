# 초성체 다중 후보 복원

초성체는 음절의 중성·종성 정보를 버리므로 기존 `normalize_korean()`의 무손실 규칙처럼 원문을
유일하게 복원할 수 없다. 예를 들어 같은 `ㅈㅎ`가 진행·전화·제한·전환 등 여러 단어가 될 수 있다.
따라서 기본 정규화 함수는 초성체를 계속 보존하고, 별도 후보 생성기가 원문 view와 제한된 복원
view를 함께 제공한다.

## 설계 경계

- benchmark 원문을 사전으로 만들지 않는다.
- 원문 view는 항상 첫 후보로 보존한다.
- 후보는 호출자가 제공한 일반 어휘 빈도순 사전에서만 가져온다.
- 완전 초성 토큰과 `ㅅ정ㅇ` 같은 부분 초성 토큰을 모두 지원한다.
- 기본값은 초성이 3개 이상인 span만 확장한다.
- `ㅋㅋ`, `ㅎㅎㅎ`처럼 같은 초성이 반복된 통신체는 확장하지 않는다.
- primitive는 한 span당 3개, 문장당 원문 포함 최대 16개로 후보 폭발을 제한한다.
- 실제 Gateway 기본 총 view 예산은 평가로 선택한 10개이며 호출자가 재정의할 수 있다.
- 후보 상한은 direct, segmented, partial 순으로 배정해 확장 정책이 이전 후보를 밀어내지 않는다.
- 복원 후보에는 `lossy=true`, 원문 offset, 사전 rank와 대안 수를 기록한다.

기본 정규화와 분리한 이유는 정상 입력을 조용히 다른 문장으로 바꾸지 않기 위해서다. 실제 gateway는
원문과 후보들을 같은 가드레일로 판정하고 집계 규칙을 별도 사전등록해야 한다. 단순 OR 판정은 탐지율과
오탐을 함께 높일 수 있으므로 ΔFPR 평가 전에는 기본 동작으로 활성화하지 않는다.

## API

```python
from k_safeguard import ChosungLexicon, generate_chosung_candidates

lexicon = ChosungLexicon(["시스템", "산사태", "설정을", "설정은"])
result = generate_chosung_candidates("ㅅㅅㅌ 점검", lexicon)

for candidate in result.candidates:
    print(candidate.text, candidate.lossy)
```

사용자·도메인 사전을 일반 사전보다 먼저 적용할 때는 source 순서를 명시한다. 같은 단어가 여러 source에
있으면 첫 source가 소유하며 후보 replacement에도 출처가 기록된다.

```python
from k_safeguard import ChosungLexicon, expand_korean_noun_particles

user_words = expand_korean_noun_particles(["보안정책", "시스템프롬프트"])
lexicon = ChosungLexicon.from_sources(
    [
        ("user", user_words),
        ("general", ["시스템", "산사태"]),
    ]
)
```

조사 확장은 opt-in이며 명사형 사용자 사전에만 적용한다. 기본 `ChosungLexicon(words)`와 Gateway에는
자동 적용되지 않는다. `k-safeguard[wordfreq]` 사용자는 `WordfreqChosungProvider`의
`priority_words`와 `expand_priority_particles=True`로 같은 구성을 만들 수 있다.

사전에 긴 복합어 전체가 없을 때는 완전 초성 span 분할을 별도로 활성화할 수 있다. 기본 분할 한도는
2개 segment, segment당 후보 1개이며 기존 문장 후보 상한을 그대로 적용한다.

```python
from k_safeguard.providers import ChosungLexiconProvider

provider = ChosungLexiconProvider(
    lexicon,
    allow_segmentation=True,
    max_segments=2,
    max_options_per_segment=1,
)
```

부분 초성·완성형 음절이 섞인 span은 분할하지 않으며 직접 일치만 사용한다. 분할된 replacement에는
`segment_words`, `segment_sources`가 기록되고 provider metadata에는 최대 segment 수가 포함된다.

긴 완전 초성 span에서 신뢰한 사전 단어 한 구간만 복원하는 실험 기능도 opt-in으로 사용할 수 있다.
일반 빈도 사전의 우연한 부분 일치를 막기 위해 `partial_sources`를 반드시 지정해야 하며, 기본 후보당
부분 복원은 한 번으로 제한된다.

```python
provider = ChosungLexiconProvider(
    lexicon,
    allow_partial_restoration=True,
    partial_sources=("user",),
    min_partial_initials=3,
    max_partial_replacements=1,
)
```

이 기능은 현재 benchmark에서 복원률을 개선하지 못했으므로 기본 활성화하거나 방어 개선으로 해석하지
않는다. 비교 결과는
[`experiments/benchmark/CHOSUNG_PARTIAL_RESTORATION_COMPARISON.md`](./experiments/benchmark/CHOSUNG_PARTIAL_RESTORATION_COMPARISON.md)에
기록한다.

candidate generator 0.5.0은 같은 설정에서 `direct ⊆ segmented ⊆ partial` 후보 집합을 보장한다.
이전 버전에서 segmentation 활성화가 direct 후보를 밀어내던 문제와 전체 재평가 결과는
[`experiments/benchmark/CHOSUNG_CANDIDATE_MONOTONICITY.md`](./experiments/benchmark/CHOSUNG_CANDIDATE_MONOTONICITY.md)에
기록한다.

16개 전체 후보 결과를 예산별로 재집계한 결과, 총 10 view부터 공격 block rate·NRR·ΔFPR이
16과 같았다. 이에 따라 Gateway 기본 `max_views`는 10으로 낮췄다. 선택 근거와 비용 곡선은
[`experiments/benchmark/CHOSUNG_VIEW_BUDGET.md`](./experiments/benchmark/CHOSUNG_VIEW_BUDGET.md)에
기록한다.

Kanana 가드레일에 후보 view를 직접 연결한 평가에서도 segmented 대비 partial의 판정 변화는 0건이었다.
segmented의 초성 공격 block rate는 raw 18.94%에서 27.91%로 올랐지만 NRR은 13.04%에 그쳤고,
평균 추가 view 7.94개와 62.97%의 후보 상한 도달률이 관찰됐다. 따라서 모든 lossy provider는 계속
기본 비활성화한다. 상세 결과는
[`experiments/benchmark/CHOSUNG_GUARDRAIL_IMPACT.md`](./experiments/benchmark/CHOSUNG_GUARDRAIL_IMPACT.md)에
기록한다.

`ChosungLexicon`은 특정 라이브러리에 의존하지 않는다. 실험에서는 빈도순 한국어 단어를 제공하는
[`wordfreq`](https://github.com/rspeer/wordfreq) 3.1.1을 선택했다. 코드 라이선스는 Apache-2.0이며
포함 데이터에는 CC BY-SA 4.0 자료가 있으므로, 단어 목록을 별도 CSV로 복제·재배포하지 않고 런타임에
라이브러리 API를 호출한다.

## 개발용 어휘 coverage 진단

```powershell
.\.venv-experiment\Scripts\python -m pip install `
  -r experiments\guardrail\requirements-chosung.txt

.\.venv-experiment\Scripts\python `
  -m experiments.benchmark.run_chosung_lexical_diagnostic
```

진단은 후보 생성률, exact 후보 포함률, top-1 exact 비율, 초성 위치별 최대 복원률을 집계한다. 현재
benchmark와 원문은 이미 공개되어 있으므로 결과 상태는 항상 `PROVISIONAL_DEV_ONLY`다. 이 실행은 어휘
coverage 확인용이며, 문맥 이해도·semantic fidelity·가드레일 방어율을 대신하지 않는다.

기본 설정의 전체 진단 결과와 활성화 판정은
[`experiments/benchmark/CHOSUNG_LEXICAL_DIAGNOSTIC.md`](./experiments/benchmark/CHOSUNG_LEXICAL_DIAGNOSTIC.md)에
기록했다. 일반 빈도순 후보의 복원 coverage가 낮아 현재 버전은 gateway에 기본 연결하지 않는다.

실패 원인을 후보 미생성·과잉 복원 proxy·정답 후보 누락·순위 오류로 분리한 개선 전 기준선은
[`experiments/benchmark/CHOSUNG_ERROR_ANALYSIS.md`](./experiments/benchmark/CHOSUNG_ERROR_ANALYSIS.md)에
기록한다. 후속 provider 개선은 같은 `chosung-error-v1` taxonomy로 비교한다.

사용자·도메인 사전 50개와 조사 확장을 일반 빈도 사전과 비교한 결과는
[`experiments/benchmark/CHOSUNG_LEXICON_COMPARISON.md`](./experiments/benchmark/CHOSUNG_LEXICON_COMPARISON.md)에
기록한다. 평균 초성 위치 복원은 0.92%p 올랐지만 문장 exact 성공은 여전히 0건이므로 기본 활성화는
계속 보류한다.

긴 완전 초성 span을 사전 항목 2개로 분할한 비교는
[`experiments/benchmark/CHOSUNG_SEGMENTATION_COMPARISON.md`](./experiments/benchmark/CHOSUNG_SEGMENTATION_COMPARISON.md)에
기록한다. 평균 초성 위치 복원은 control 대비 4.32%p 개선됐지만 exact 성공은 0건이므로 이 기능도
opt-in으로 유지한다.
