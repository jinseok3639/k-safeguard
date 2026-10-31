# k-safeguard

**난독화된 한국어를 원래 문장으로 되돌리는 정규화기입니다.**

자모를 쪼개거나 소리 나는 대로 적은 한국어를 사람은 쉽게 읽지만, 프로그램은 다른 문자열로 봅니다.
k-safeguard는 이런 표기를 되돌려 검색, 필터, 분류기, 가드레일 앞단에 놓을 수 있게 합니다.

```python
from k_safeguard import Gateway

Gateway().normalize("ㅅㅣㅅㅡㅌㅔㅁ 점검")   # '시스템 점검'
```

[브라우저에서 직접 시험하기](https://jinseok3639.github.io/k-safeguard/){ .md-button .md-button--primary }
[튜토리얼 시작하기](tutorial/normalize.md){ .md-button }

## 설치

```bash
python -m pip install k-safeguard
```

기본 설치에는 런타임 의존성이 없습니다. 문맥을 보고 복원하는 모델이 필요할 때만 extra를 추가합니다.

```bash
python -m pip install "k-safeguard[ml-restore]"
```

## 처리 흐름

```text
입력
 ├─ 무손실 정규화       의미가 바뀌지 않는 표기 변형만 되돌립니다
 ├─ provider (opt-in)   직접 넣은 provider가 복원 후보를 만듭니다
 ▼
normalize()   정규화된 문장 하나
process()     원문, 정규화문, 후보 전체와 변경 내역
evaluate()    전체 view를 분류기로 판정해 OR로 집계
```

원문은 항상 첫 번째 view로 보존됩니다. k-safeguard는 차단 여부를 스스로 정하지 않으며, 판정은
연결한 분류기가 합니다.

## 어디부터 읽을까요

| 하려는 일 | 문서 |
|---|---|
| 입력을 정리해 한 문장으로 받기 | [문장 정규화](tutorial/normalize.md) |
| 복원 후보를 비교하고 변경 내역 남기기 | [후보와 변경 내역 보기](tutorial/process.md) |
| 기존 가드레일의 난독화 우회 막기 | [가드레일 연결](tutorial/guardrail.md) |
| 어떤 API를 쓸지 고르기 | [API 선택](guide/choosing-api.md) |
| 함수와 필드 찾아보기 | [API 레퍼런스](reference/index.md) |
