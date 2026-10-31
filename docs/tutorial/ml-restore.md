# 모델로 복원

된소리, 연음, 받침 변형처럼 문맥이 필요한 표기까지 되돌리려면 `MlRestoreProvider`를 씁니다. 글자마다 유지, 삭제,
교체를 예측하고, 확신이 임계값에 못 미치는 글자는 그대로 둡니다.

```bash
python -m pip install "k-safeguard[ml-restore]"
```

```python
from k_safeguard import Gateway
from k_safeguard.providers.ml_restore import MlRestoreProvider

gateway = Gateway(providers=[MlRestoreProvider.from_pretrained()])
gateway.normalize("요리 만뜨는 뻡 알려쭤")
```

## 가중치 받기

| 방법 | 설명 |
|---|---|
| `from_pretrained()` | GitHub Release에서 약 500MB를 받아 파일마다 sha256을 검증하고 OS 캐시에 저장합니다 |
| `from_directory(path)` | 직접 준비한 가중치를 읽습니다. 디렉터리에 `manifest.json`이 있어야 합니다 |

코드는 Apache-2.0이지만 `from_pretrained()`로 받는 가중치의 라이선스는 CC BY-SA 4.0입니다.
[출처와 고지](https://github.com/jinseok3639/k-safeguard/blob/main/tools/release/WEIGHTS_LICENSE.md)를 확인하세요.

## 결과 사용하기

```python
gateway.normalize(text)            # 후보가 있으면 복원문, 없으면 정규화문
gateway.process(text)              # 원문과 복원문을 함께 확인
gateway.evaluate(text, guardrail)  # 원문과 복원문을 모두 판정
```

후보는 입력당 최대 하나이고 항상 lossy입니다. 모델도 정상 문장을 바꿀 수 있으므로, 원문이 중요하면 `process()`로
원문과 함께 다룹니다.

## 대량 처리

```python
provider = MlRestoreProvider.from_pretrained()
provider.restore_batch(sentences)   # [(복원문, 적용 편집 수, 평균 확신도), ...]
```

`restore_batch()`는 긴 입력을 나누지 않습니다. 긴 문장은 `restore()`로 처리합니다.

참고: [`MlRestoreProvider`][k_safeguard.providers.ml_restore.MlRestoreProvider]
