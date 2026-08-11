# k-safeguard 패키징과 런타임 경계

`k-safeguard`는 특정 LLM이나 GPU 환경에 종속되지 않는 전처리 gateway 라이브러리다. 배포
distribution 이름은 `k-safeguard`, Python import 이름은 `k_safeguard`다.

## 설치 계층

| 설치 | 포함 | 기본 활성화 |
|---|---|---|
| `k-safeguard` | 무손실 정규화, Gateway, provider protocol, 초성 후보 primitive | 무손실 core만 |
| `k-safeguard[wordfreq]` | `wordfreq` 기반 실험적 초성 provider | 아니요, 명시적 주입 필요 |
| 외부 provider | 형태소 분석기, 로컬·원격 복원기, 사용자 사전 | 사용자 정책에 따름 |

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

```python
from k_safeguard import ChosungLexicon, Gateway
from k_safeguard.providers import ChosungLexiconProvider

provider = ChosungLexiconProvider(ChosungLexicon(["시스템", "산사태"]))
result = Gateway(providers=[provider], max_views=4).process("ㅅㅅㅌ 점검")
```

provider 오류는 기본적으로 `provider_errors`에 기록하고 원문·무손실 view를 반환한다. 배포 정책상
오류를 즉시 전파해야 하면 `strict_providers=True`를 사용한다.

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
├── normalization.py
├── chosung.py
├── gateway.py
├── py.typed
└── providers/
    ├── chosung.py
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
