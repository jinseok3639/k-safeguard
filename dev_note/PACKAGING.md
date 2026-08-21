# k-safeguard 패키징과 런타임 경계

`k-safeguard`는 특정 LLM이나 GPU 환경에 종속되지 않는 전처리 gateway 라이브러리다. 배포
distribution 이름은 `k-safeguard`, Python import 이름은 `k_safeguard`다.

## 설치 계층

| 설치 | 포함 | 기본 활성화 |
|---|---|---|
| `k-safeguard` | 무손실 정규화, Gateway, provider protocol, 초성 후보 primitive, `TensifyInverseProvider`(된소리 역변형, 무의존) | 무손실 core만 |
| `k-safeguard[wordfreq]` | `wordfreq` 기반 실험적 초성 provider | 아니요, 명시적 주입 필요 |
| 외부 provider | 형태소 분석기, 로컬·원격 복원기, 사용자 사전 | 사용자 정책에 따름 |

`TensifyInverseProvider`는 core wheel에 포함되지만 opt-in provider라 기본 Gateway에 자동 연결되지
않는다. 추가 dependency 없이 `Gateway(providers=[TensifyInverseProvider(...)])`로 주입한다.

기본 wheel은 외부 런타임 dependency가 0개다. `torch`, `transformers`, 가드레일 모델과 복원 모델은
프로젝트 평가 환경 또는 사용자가 선택한 별도 provider에 속하며 패키지 dependency로 선언하지 않는다.

## public API

```python
from k_safeguard import Gateway, normalize_korean

normalized = normalize_korean("ㅇㅏㄴㄴㅕㅇ")
result = Gateway().process("ㅇㅏㄴㄴㅕㅇ")
```

`GatewayResult.views`의 첫 항목은 항상 원문이다. 무손실 정규화가 실제로 바뀐 경우 두 번째 view로
추가된다. 후보 provider는 opt-in이며 모든 후보에는 provider, `lossy`, confidence와 metadata가 붙는다.
기본 `max_views`는 10이며 원문·무손실 정규화문·모든 provider 후보를 합친 총 예산이다. 개발
benchmark에서 16과 같은 방어 지표를 유지한 최소 관측 예산이며, 서비스 요구에 따라 명시적으로
재정의할 수 있다.

```python
from k_safeguard import ChosungLexicon, Gateway
from k_safeguard.providers import ChosungLexiconProvider

provider = ChosungLexiconProvider(ChosungLexicon(["시스템", "산사태"]))
result = Gateway(providers=[provider]).process("ㅅㅅㅌ 점검")
```

provider 오류는 기본적으로 `provider_errors`에 기록하고 원문·무손실 view를 반환한다. 배포 정책상
오류를 즉시 전파해야 하면 `strict_providers=True`를 사용한다.

## 가드레일 실행

후보 view 생성뿐 아니라 외부 가드레일 호출과 OR 집계까지 맡길 수 있다. callable은 `bool` 또는
`ClassifierResult`를 반환하며, 첫 block에서 기본적으로 조기 종료한다.

```python
from k_safeguard import Gateway

decision = Gateway().evaluate(
    "사용자 입력",
    lambda text: external_guardrail(text).blocked,
)
```

원격 async client는 같은 정책을 유지하는 비동기 API에 직접 연결할 수 있다.

```python
async def classifier(text: str) -> bool:
    response = await external_guardrail.classify(text)
    return response.blocked

decision = await Gateway().evaluate_async("사용자 입력", classifier)
```

여러 후보 view를 한 번의 로컬 모델 호출이나 batch endpoint로 처리하려면 같은 길이의 판정 iterable을
반환하는 batch callable을 사용한다.

```python
def batch_classifier(texts: tuple[str, ...]):
    return [item.blocked for item in external_guardrail.classify_batch(texts)]

decision = Gateway().evaluate_batch(
    "사용자 입력",
    batch_classifier,
    batch_size=4,
)
```

classifier 오류 기본 정책은 `raise`다. fail-closed가 필요하면 `error_mode="block"`, 별도 장애 격리가
있는 환경에서만 `error_mode="allow"`를 명시한다. 전체 계약과 trace 스키마는
[실행·집계 API 문서](./EXECUTION.md)를 참고한다.

## 외부 provider 계약

provider는 모델 종류, 동기화 방식이나 가드레일 구현을 강제하지 않는 최소 protocol을 구현한다.

```python
from k_safeguard import CandidateProposal

class MyProvider:
    name = "my_provider"

    def generate(self, text):
        yield CandidateProposal(
            text="후보 문자열",
            lossy=True,
            confidence=0.7,
        )
```

원격 API, 사내 모델과 로컬 Transformers 모델은 모두 이 경계 밖에서 초기화한다. 이 구조를 통해
CPU-only 환경은 core만 설치하고, GPU 사용자는 자신에게 맞는 provider를 별도 배포할 수 있다.

## 소스 구조

```text
src/k_safeguard/
├── __init__.py
├── execution.py
├── normalization.py
├── chosung.py
├── gateway.py
├── py.typed
└── providers/
    ├── __init__.py
    ├── chosung.py
    ├── tensify.py
    └── wordfreq.py
```

`experiments/`의 Kanana·Qwen adapter와 모델 requirements는 wheel에 포함되지 않는다.

## 로컬 빌드 검증

```bash
python -m pip install --upgrade build
python -m build
python tools/release/verify_artifacts.py
python -m pip install --force-reinstall --no-deps dist/k_safeguard-0.1.0-py3-none-any.whl
python -m unittest discover -s tests -v
```

PR CI는 Windows, Linux, macOS와 지원 Python 버전에서 editable 설치, core 테스트, wheel 빌드와 wheel
재설치를 확인한다. PyPI 배포 전에는 수동 승인형 TestPyPI workflow에서 같은 설치 검증을 한 번 더
수행한다. 버전 변경, Trusted Publisher 최초 설정과 배포 순서는 [릴리스 절차](./RELEASING.md)를 따른다.
