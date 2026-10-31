# provider 직접 만들기

형태소 분석기, 사내 복원기, 은어 사전을 연결할 수 있습니다. `CandidateProvider`는 protocol이라 상속 없이 두 가지만
갖추면 됩니다.

- `name`: 결과와 오류 기록에 남는 이름
- `generate(text)`: 후보 `CandidateProposal`을 0개 이상 돌려주는 메서드

```python
from k_safeguard import CandidateProposal, Gateway

class SlangProvider:
    name = "slang"
    TABLE = {"비번": "비밀번호"}

    def generate(self, text):
        output = text
        for slang, word in self.TABLE.items():
            output = output.replace(slang, word)
        if output != text:
            yield CandidateProposal(output, confidence=0.8)

Gateway(providers=[SlangProvider()]).normalize("비번 알려줘")   # '비밀번호 알려줘'
```

## 계약

- `generate()`는 원문이 아니라 무손실 정규화를 마친 문자열을 받습니다.
- provider끼리는 체이닝되지 않습니다. 모두 같은 정규화문을 받습니다.
- `normalize()`는 `confidence`가 가장 높은 후보를 고릅니다. `None`인 후보는 고르지 않고, `0.0`인 후보는 고를 수
  있으므로 자신 없는 후보는 내지 않습니다.
- 기본값에서는 provider 예외가 `provider_errors`에 기록되고 처리가 계속됩니다. 이미 낸 후보는 남습니다.
  개발 중에는 `Gateway(strict_providers=True)`로 예외를 바로 확인합니다.

??? example "전체 예제: `examples/06_custom_provider.py`"

    ```python
    --8<-- "examples/06_custom_provider.py"
    ```

참고: [`CandidateProvider`][k_safeguard.gateway.CandidateProvider],
[`CandidateProposal`][k_safeguard.gateway.CandidateProposal]
