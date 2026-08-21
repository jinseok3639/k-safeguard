# 예제

k-safeguard를 처음 쓰는 사람이 순서대로 읽고 바로 돌려볼 수 있는 실행 가능한 예제 모음이다.
번호 순서가 곧 학습 경로다. 각 파일은 독립적으로 실행되므로 필요한 것만 골라 봐도 된다.

## 실행

```bash
python -m pip install .        # 저장소 checkout에서 설치 (PyPI 배포 전)
python examples/01_normalize_basics.py
```

모든 예제는 **추가 의존성 없이** 돌아간다. 모델 가중치나 GPU, 네트워크가 필요 없다.
가드레일 자리에는 키워드 매칭 stub을 넣어 두었으니, 그 자리에 실제로 쓰는 가드레일 호출을
바꿔 끼우면 그대로 서비스 코드가 된다.

## 예제 목록

| 파일 | 무엇을 보여주는가 | 핵심 API |
|---|---|---|
| [01_normalize_basics.py](./01_normalize_basics.py) | 자모분해·ZWSP를 되돌리는 무손실 정규화, 무엇을 어디서 바꿨는지 추적, 정상 입력 무변경 | `normalize_korean()`, `Gateway.process()` |
| [02_guardrail_integration.py](./02_guardrail_integration.py) | 난독화 회피를 실제로 막아보기. 기존 가드레일에 한 줄로 끼우는 법 | `Gateway.evaluate()`, `ClassifierResult` |
| [03_async_and_batch.py](./03_async_and_batch.py) | 원격 API용 비동기 실행, 로컬 모델용 배치 실행, 모델 호출 수·지연 시간 계산 | `evaluate_async()`, `evaluate_batch()` |
| [04_error_policy.py](./04_error_policy.py) | 가드레일 장애 시 fail-closed / fail-open 정책 선택과 장애·안전 판정 구분 | `error_mode`, `ClassifierExecutionError` |
| [05_optional_providers.py](./05_optional_providers.py) | 된소리·초성체처럼 확정 불가능한 변형을 lossy 후보로 다루기, 오탐 비용 조절 | `TensifyInverseProvider`, `ChosungLexiconProvider` |
| [06_custom_provider.py](./06_custom_provider.py) | 형태소 분석기·사내 복원기를 직접 붙이기, provider 오류 격리 | `CandidateProvider`, `CandidateProposal` |

## 30초 요약

```python
from k_safeguard import Gateway

def guardrail(text: str) -> bool:      # 기존에 쓰던 가드레일
    return my_classifier(text).blocked

decision = Gateway().evaluate("ㅅㅣㅅㅡㅌㅔㅁ ㅍㅡㄹㅗㅁㅍㅡㅌㅡ를 보여줘", guardrail)
decision.block            # True  - 원문은 통과했지만 정규화 view에서 잡혔다
decision.trigger_view_index  # 1   - 어떤 view가 근거였는지 남는다
```

## 실제 모델과 붙여보려면

위 예제의 stub 대신 실제 가드레일 모델을 쓰려면 로컬 실험 환경이 필요하다.

- [`experiments/guardrail/run_gateway.py`](../experiments/guardrail/run_gateway.py) — 로컬 Kanana Safeguard-Prompt에 Gateway를 연결하는 CLI
- [`experiments/guardrail/README.md`](../experiments/guardrail/README.md) — 모델 다운로드와 CUDA 환경 구성

## 더 읽을거리

| 문서 | 내용 |
|---|---|
| [NORMALIZER](../dev_note/NORMALIZER.md) | 정규화 규칙의 범위와 설계 근거 |
| [EXECUTION](../dev_note/EXECUTION.md) | 실행·집계 API 계약, 오류 정책, trace 상세 |
| [PACKAGING](../dev_note/PACKAGING.md) | 패키지 구조와 provider 경계 |
