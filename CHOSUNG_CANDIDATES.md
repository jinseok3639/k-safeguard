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
- 한 span당 3개, 문장당 원문 포함 16개로 후보 폭발을 제한한다.
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
