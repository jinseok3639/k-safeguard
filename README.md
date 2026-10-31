<div align="center">

# k-safeguard

**난독화된 한국어를 원래 문장으로 되돌리는 정규화기**

[![Python package](https://github.com/jinseok3639/k-safeguard/actions/workflows/package.yml/badge.svg)](https://github.com/jinseok3639/k-safeguard/actions/workflows/package.yml)
[![Branch coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/jinseok3639/k-safeguard/badges/branch-coverage.json&cacheSeconds=300)](https://github.com/jinseok3639/k-safeguard/actions/workflows/coverage.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](https://github.com/jinseok3639/k-safeguard/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](https://github.com/jinseok3639/k-safeguard/blob/main/pyproject.toml)

**한국어** · [English](https://github.com/jinseok3639/k-safeguard/blob/main/README.en.md) &nbsp;|&nbsp; [벤치마크 데이터셋](https://huggingface.co/datasets/kimchunsik03/KoreanGuardrail) · [실험 저장소](https://github.com/jinseok3639/k-safeguard-ML-experiment)

[브라우저에서 직접 시험하기](https://jinseok3639.github.io/k-safeguard/) — 입력을 서버에 전송하지 않는 정규화 playground · [API 문서](https://jinseok3639.github.io/k-safeguard/docs/)

</div>

---

## 왜 필요한가

한국어는 자모를 쪼개거나 소리 나는 대로 적어도 사람은 쉽게 읽지만, 프로그램은 다른 문자열로 본다.
검색, 필터, 분류기, 언어 모델처럼 텍스트를 처리하는 시스템은 이런 표기 앞에서 원래 의미를 놓친다.
k-safeguard는 이 표기를 원래 문장으로 되돌려 그 앞단에 놓을 수 있게 한다.

```python
from k_safeguard import Gateway

Gateway().normalize("ㅅㅣㅅㅡㅌㅔㅁ 점검")     # → "시스템 점검"
```

## 설치

```bash
python -m pip install k-safeguard
```

기본 설치에는 **런타임 의존성이 없다.** Torch, Transformers, 모델 가중치를 요구하지 않으므로 기존 서비스에 그대로 얹을 수 있다.

문맥을 보고 복원하는 모델은 extra로 분리돼 있다 — `k-safeguard[ml-restore]`(`onnxruntime`·`numpy`·`tokenizers`). 처음 쓸 때 가중치 약 500MB를 받으며, 기본 Gateway에 자동 연결되지 않는다.

## 빠른 시작

### 1. 규칙 기반 정규화

추가 의존성 없이 확정할 수 있는 표기 변형만 되돌린다.

```python
from k_safeguard import Gateway

assert Gateway().normalize("ㅇㅏㄴㄴㅕㅇ") == "안녕"
```

### 2. 모델로 복원하기

된소리, 연음, 받침 변형처럼 문맥이 필요한 표기까지 되돌린다.

```python
from k_safeguard import Gateway
from k_safeguard.providers.ml_restore import MlRestoreProvider

gateway = Gateway(providers=[MlRestoreProvider.from_pretrained()])
gateway.normalize("요리 만뜨는 뻡 알려쭤")
```

### 3. 후보와 변경 내역 보기

`process()`는 원문, 정규화문, 복원 후보를 모두 돌려준다. 복원문을 그대로 믿기 어려운 경우에는 이쪽을 쓴다.

```python
result = Gateway().process("ㅇㅏㄴㄴㅕㅇ")

assert result.views[0].text == "ㅇㅏㄴㄴㅕㅇ"     # 원문은 항상 첫 번째
assert result.normalized == "안녕"
```

실행 가능한 예제는 [`examples/`](https://github.com/jinseok3639/k-safeguard/blob/main/examples/README.md)에 있다.

## 동작 방식

```text
입력
 │
 ├─ 무손실 정규화       확정 가능한 표기 변형만 되돌린다 (원문 의미 불변)
 │
 ├─ provider (opt-in)   모델·규칙으로 복원 후보를 만든다
 ▼
normalize() → 정규화된 문장 하나
process()   → 원문·정규화문·후보 목록
evaluate()  → 목록 전체를 분류기로 판정 (가드레일 연결)
```

핵심 설계 원칙은 **원문을 절대 잃지 않는다**는 것이다. 무손실로 확정할 수 없는 된소리는
원문 그대로 두며, 공개 Gateway가 자체적으로 여러 복원 view를 만들지 않는다.

### 기본 정규화 규칙 (무손실)

| rule ID | 처리 대상 | 정책 |
|---|---|---|
| `remove_hangul_zwsp` | 한글·자모와 인접한 U+200B ZERO WIDTH SPACE | U+200B만 제거 |
| `normalize_halfwidth_hangul` | U+FFA1–U+FFDC의 현대 반각 한글 자모 | 표준 호환 자모로 변환 후 음절 조합 |
| `compose_modern_jamo` | `안` 같은 현대 조합형 자모열 | 음절로 조합 |
| `compose_compat_jamo` | `ㅇㅏㄴ` 같은 호환 자모열 | 모음 경계 확인 후 조합 |

이 규칙은 범용 투명문자 제거기가 아니다. U+200C ZWNJ, U+200D ZWJ, U+2060 WORD JOINER,
U+FEFF BOM, U+00AD SOFT HYPHEN은 한글·자모 사이에 있어도 보존한다. 또한 전역 NFC를 적용하지 않고
지원 범위의 한글 자모열만 조합한다. 반각 한글 filler·반각 가타카나·전각 라틴 등도 보존하므로
emoji ZWJ, 결합문자, 한영 코드스위칭 입력을 임의로 훼손하지 않는다. 자세한 내용은
[정규화기 문서](https://github.com/jinseok3639/k-safeguard/blob/main/dev_note/NORMALIZER.md).

### 모호한 변형 처리 정책

문맥 없이는 원문을 확정할 수 없는 변형은 기본 Gateway에서 복원하지 않는다. 연음 provider는
명시적 opt-in으로만 제공한다.
띄어 쓴 자모와 ML 복원도 정보 손실이 있어 기본 Gateway에는 자동 연결하지 않는다.

| provider | 대상 | 추가 의존성 | 현재 상태 |
|---|---|---|---|
| `LiaisonInverseProvider` | `머글게` 같은 단순 연음 표기 | 없음 | 개발 NRR 56.52%, 평균 +8.08 view·ΔFPR 관찰로 기본 비활성 |
| `SpacedJamoProvider` | `ㅇ ㅓ ㅂ ㅅ ㅇ ㅣ`처럼 공백으로 분리된 자모 | 없음 | 한 어절 개발 exact 504/504, 공백 삭제는 lossy라 기본 비활성 |
| `MlRestoreProvider` | 글자 교체·삭제와 띄어쓰기를 포함한 복합 난독화 | `ml-restore` extra + 별도 가중치 | 가중치가 크고 결과가 lossy라 기본 비활성. 수치는 [측정 결과](#측정-결과) |

#### 띄어 쓴 자모 복원 — SpacedJamoProvider

`ㅅ ㅣ ㅅ ㅡ ㅌ ㅔ ㅁ`처럼 자모를 공백으로 띄어 쓴 난독화를 되돌린다. 붙어 있는 자모만 조합하는
무손실 정규화기와 달리 공백을 먼저 걷어내며, 공백 삭제는 lossy라 원문을 덮어쓰지 않고 후보
view만 추가한다. 자모 4개 이상이 ASCII 공백으로 이어진 구간이 완성형 음절로 전부 조합될 때만
후보 하나를 낸다.

```python
from k_safeguard import Gateway
from k_safeguard.providers.spaced_jamo import SpacedJamoProvider

gateway = Gateway(providers=[SpacedJamoProvider()])
result = gateway.process("ㅅ ㅣ ㅅ ㅡ ㅌ ㅔ ㅁ 점검")

assert result.views[0].text == "ㅅ ㅣ ㅅ ㅡ ㅌ ㅔ ㅁ 점검"   # 원문 보존
assert "시스템 점검" in [v.text for v in result.views]      # 복원 후보 추가
```

#### 연음 역복원 — LiaisonInverseProvider

```python
from k_safeguard import Gateway
from k_safeguard.providers import LiaisonInverseProvider

gateway = Gateway(providers=[LiaisonInverseProvider(max_candidates=9)])
result = gateway.process("머글게")

assert result.views[0].text == "머글게"                    # 원문 보존
assert "먹을게" in [view.text for view in result.views]    # 복원 후보 추가
```

연음 역복원은 자연어에도 같은 표면 패턴이 많으므로 원문을 덮어쓰지 않고 lossy 후보로만 추가한다.

#### 규칙 provider와 ML provider의 차이

`LiaisonInverseProvider`는 되돌릴 수 있는 **조합을 나열**한다. 어느 것이 맞는지는 판단하지 않으며 후보마다 `confidence=None`을 사용한다.

`MlRestoreProvider`는 KcELECTRA 기반 글자 편집 태거로 **글자마다 유지·삭제·교체를 판단하고**, 확신이 임계값에 못 미치는 글자는 건드리지 않는다(abstention). 그래서 후보를 하나만 낸다.

```python
from k_safeguard import Gateway
from k_safeguard.providers.ml_restore import MlRestoreProvider

# GitHub Release에서 받아 로컬 캐시에 저장한다(파일마다 sha256 검증)
gateway = Gateway(providers=[MlRestoreProvider.from_pretrained()])
result = gateway.process("요리 만뜨는 뻡 알려쭤")

assert result.views[0].text == "요리 만뜨는 뻡 알려쭤"   # 원문 보존
```

##### 모델 가중치

저장소 정책상 모델 체크포인트는 Git과 wheel에 넣지 않는다. `k-safeguard[ml-restore]`는 **추론 런타임만** 설치하며, 가중치는 두 가지 방법으로 받는다.

- **`from_pretrained()`** — GitHub Release에서 약 500MB를 받는다. 파일마다 `PRETRAINED_MANIFEST`에 고정된 sha256·크기로 검증하고 OS 캐시 디렉터리에 저장해 재사용한다.
- **`from_directory(path)`** — 직접 준비한 가중치를 쓸 때. 디렉터리의 `manifest.json`은 `PRETRAINED_MANIFEST`와 형식이 같다.

인코더는 [`beomi/KcELECTRA-base-v2022`](https://huggingface.co/beomi/KcELECTRA-base-v2022)(MIT)를 미세조정했다.

## 측정 결과

### 복원 모델

`Gateway`와 같은 경로(무손실 정규화 후 문장 단독, CPU onnxruntime)로 평가셋 v1을 쟀다. 복원 대상 유형만 든 13,344문장과 평가 원문 695문장이 기준이고, 모든 문장은 프로젝트 생성기로 만들었다.

| 지표 | 결과 |
|---|---:|
| 글자 단위 F1 | **85.2%** |
| 문장별 복원율 | 78.9% |
| 완전 복원 / 나빠진 문장 | 45.6% / 1.0% |
| 정상 문장 오변경 | 0.72% (5/695) |
| 지연 p50 / p95 (CPU) | 13ms / 18ms |

### 규칙 기반 정규화

| 검증 | 결과 |
|---|---|
| ZWSP 문자열 정확 복원 | 505/505 (강도 0.5·1.0 각각) |
| 자모분해 문자열 정확 복원 | 1,008/1,008 (겹받침 낱자형 포함) |
| 반각 현대 한글 음절 전수 복원 | 11,172/11,172 |
| 정상 입력 변조율(clean mutation) | 0% — clean 505행 전부 무변경 |

## 활용: 가드레일 앞단에 붙이기

정규화의 대표적인 쓰임 중 하나는 난독화로 프롬프트 가드레일을 우회하는 입력을 막는 것이다.
505개 독립 시드(공격 301 / 정상 204)를 `kakaocorp/kanana-safeguard-prompt-2.1b`에 그대로 통과시키면 표기만 바꿔도 차단율이 무너진다.

| 입력 | 공격 차단율 |
|---|---:|
| 정상 표기 (난독화 없음) | **94.02%** |
| 된소리화 강도 1.0 — 프롬프트 인젝션(A1) | 10.31% |
| 된소리화 강도 1.0 — 프롬프트 리킹(A2) | 20.56% |

상태: `PROVISIONAL_DEV_ONLY`. 공개 개발 벤치마크의 결과이며 locked test 성능으로 해석하지 않는다([run `tensify-impact-v1-20260811`](https://github.com/jinseok3639/k-safeguard/blob/f6ee374/experiments/benchmark/TENSIFY_GUARDRAIL_IMPACT.md)).

k-safeguard는 방어 레이어 중 하나이며 가드레일 우회의 완전한 해법이 아니다.

`evaluate()`는 원문과 정규화 view를 모두 분류기에 넘겨 하나라도 걸리면 차단한다. classifier는 문자열을 받아 `bool`을 돌려주는 callable이면 되고, 판정은 k-safeguard가 아니라 기존 가드레일이 한다.

```python
decision = Gateway().evaluate("사용자 입력", lambda text: guardrail(text).blocked)

if decision.block:
    raise PermissionError("guardrail blocked")

# 원격 async client
decision = await Gateway().evaluate_async("사용자 입력", async_classifier)

# 여러 view를 한 번에 (모델 호출 수 절감)
decision = Gateway().evaluate_batch(
    "사용자 입력",
    lambda texts: [item.blocked for item in guardrail.classify_batch(texts)],
    batch_size=4,
)
```

오류 정책(`ClassifierErrorMode`), 조기 종료, view 단위 trace는 [실행·집계 API](https://github.com/jinseok3639/k-safeguard/blob/main/dev_note/EXECUTION.md)를 참고한다.

### 가드레일 평가

아래는 규칙 기반 정규화의 결과다. 현재 복원 모델의 가드레일 회복량은 아직 측정하지 않았다.

문자열 수치는 505개 독립 시드에서 파생한 현재 5,555행 벤치마크에서 재현 가능하다. Kanana 자모분해
수치는 겹받침 낱자형 복원을 적용해 실행한 `normalizer-eval-jamo-compound-counts-20260823`, ZWSP 수치는
생성 방식이 동일한 `normalizer-eval-full-20260808` 스냅샷에 고정한다.

문자열 복원과 가드레일 판정은 서로 다른 지표로 분리한다. 결과 지위는 공개 505개 시드의 개발 모집단 근거다.

| Kanana 가드레일 판정 | E1 raw 차단 | E2 정규화 차단 | clean에서 생긴 회피 variant 복원 |
|---|---:|---:|---:|
| 자모분해 낱자형, 두 강도 합산 | 569/602 (94.52%) | 566/602 (94.02%) | 15/15 |
| ZWSP, 두 강도 합산 | 564/602 (93.69%) | 566/602 (94.02%) | 19/19 |

겹받침 수정 후 자모분해 exact restoration은 1,008/1,008(100%)이며, clean에서 새로 생긴 회피
variant 15개도 모두 복원했다. E2는 clean E0 판정으로 돌아가므로 난독화가 우연히 추가 차단한 공격과
놓친 정상문도 함께 원래 판정으로 되돌린다. 따라서 순 차단율과 NRR·문자열 정확 복원을 같은 지표로
해석하지 않는다. 상세 분모와 intensity별 결과는
[모집단 평가 결과](https://github.com/jinseok3639/k-safeguard/blob/f6ee374/experiments/benchmark/NORMALIZER_POPULATION_RESULT.md)에 있다.

| 기타 검증 | 결과 |
|---|---|
| 종단 간 회복 smoke (Kanana 실제 호출) | 난독화 fixture 4/4가 raw allow → 정규화 view에서 block |
| batch 추론 | view 20개 판정 parity 유지, 호출 90%·wall time 74.3% 감소 |

> **해석 제한**: 종단 간 smoke는 회복이 확인된 fixture를 의도적으로 고른 회귀 검증이므로 모집단 성능 추정에 쓰지 않는다.
> 전체 E0/E1/E2/E3 평가 중 Prompt 가드레일 판정만 유효하며, 하위 LLM의 intent-recognition·semantic fidelity와 실제 공격 성공률 평가는 `INCOMPLETE` 상태다.
> 평가 규격은 [EVALUATION_SPEC](https://github.com/jinseok3639/k-safeguard/blob/main/dev_note/EVALUATION_SPEC.md), 실행 절차는 [정규화 평가 문서](https://github.com/jinseok3639/k-safeguard/blob/f6ee374/experiments/benchmark/NORMALIZER_EVALUATION.md)를 따른다.

## 스코프와 한계

**다루는 것** — 한국어 표기 난독화(자모분해·된소리·연음·종성크래밍·띄어쓰기 파괴·기호 삽입·투명문자)의 정규화.

**한계**

- 모델은 학습에 없던 모양에 약하다. 다른 생성기(KOTOX·kotka)로 만든 문장에서는 글자 단위 F1이 63.0%, 문장별 복원율이 53.8%다.
- 모델은 정상 문장도 바꿀 수 있고, 외래어·기술 용어에서 오류가 주로 나온다. 원문이 중요하면 `process()`로 원문과 함께 다룬다.
- 평가 문장은 일반 텍스트 전반을 대표하지 않는다. 뉴스·커뮤니티 글 같은 다른 영역에서는 재지 않았다.
- 모델을 올리면 메모리가 약 520MB 늘어난다. 긴 입력은 약 12,000자(384자 × 32조각)까지만 복원하고 나머지는 그대로 둔다.

**다루지 않는 것**

- 초성체 — 초성만 남으면 원문 정보가 대부분 사라진다. 복원하지 않고 원문 그대로 둔다
- 타 언어 표기, 멀티모달 입력
- 판정 — k-safeguard는 block/allow를 스스로 정하지 않는다

## 함께 제공하는 것

| 산출물 | 위치 | 설명 |
|---|---|---|
| 실행 가능한 예제 | [`examples/`](https://github.com/jinseok3639/k-safeguard/blob/main/examples/README.md) | 정규화, provider 확장, 가드레일 연결, 비동기/배치, 오류 정책 샘플 코드 |
| 난독화 생성기 | [`k_safeguard.obfuscate`](https://github.com/jinseok3639/k-safeguard/blob/main/src/k_safeguard/obfuscate.py) | 기법 24종의 강도·시드별 변형 생성기. 정규화기를 시험하거나 평가 데이터를 만들 때 쓴다. 닮은 글자 사전은 [KOTOX](https://github.com/leeyejin1231/KOTOX)(MIT) |
| 벤치마크 데이터셋 | [HF: KoreanGuardrail](https://huggingface.co/datasets/kimchunsik03/KoreanGuardrail) | 시드 505개 → 파생 5,555행. 데이터 CC-BY-4.0 |
| 실험 | [k-safeguard-ML-experiment](https://github.com/jinseok3639/k-safeguard-ML-experiment) | 복원기·가드레일 실험 러너와 결과 기록 |

## 문서

| 문서 | 내용 |
|---|---|
| [NORMALIZER](https://github.com/jinseok3639/k-safeguard/blob/main/dev_note/NORMALIZER.md) | 정규화 규칙, 지원 범위, 벤치마크 검증 |
| [EXECUTION](https://github.com/jinseok3639/k-safeguard/blob/main/dev_note/EXECUTION.md) | 분류기 실행·집계 API, 오류 정책, trace |
| [PACKAGING](https://github.com/jinseok3639/k-safeguard/blob/main/dev_note/PACKAGING.md) | 패키지 구조, provider 경계, 배포 검증 |
| [EVALUATION_SPEC](https://github.com/jinseok3639/k-safeguard/blob/main/dev_note/EVALUATION_SPEC.md) | 지표 정의와 보고 규칙 |
| [KOREAN_OBFUSCATION_RESEARCH](https://github.com/jinseok3639/k-safeguard/blob/main/dev_note/KOREAN_OBFUSCATION_RESEARCH.md) | 한글 난독화 기법 taxonomy와 선행 조사 |

## 개발

```bash
python -m pip install -e ".[dev,mutation]"
python -m unittest discover -s tests
python -m coverage run -m unittest discover -s tests && python -m coverage report    # 분기 커버리지
mutmut run && mutmut results    # 변이 테스트
python -m pip install -e ".[docs]" && mkdocs serve    # API 문서 미리보기
```

브랜치·커밋 컨벤션은 [AGENTS.md의 Git 워크플로](https://github.com/jinseok3639/k-safeguard/blob/main/AGENTS.md#git-워크플로)를 따른다. `type(scope): 한글 설명` 형식이며 기능·실험 단위로 PR을 연다.

버그 제보·개선 제안은 [이슈 템플릿](https://github.com/jinseok3639/k-safeguard/issues/new/choose)을, 기여 절차 전반은 [CONTRIBUTING.md](https://github.com/jinseok3639/k-safeguard/blob/main/CONTRIBUTING.md)를 참고한다.

## 라이선스

코드는 [Apache License 2.0](https://github.com/jinseok3639/k-safeguard/blob/main/LICENSE), 벤치마크 데이터셋은 CC-BY-4.0, `from_pretrained()`로 받는 모델 가중치는 CC BY-SA 4.0이다([출처와 고지](https://github.com/jinseok3639/k-safeguard/blob/main/tools/release/WEIGHTS_LICENSE.md)). 가중치는 wheel에 들어 있지 않다. 패키지에 함께 들어 있는 닮은 글자 사전은 KOTOX의 것으로 MIT다.
