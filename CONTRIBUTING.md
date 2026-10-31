# 기여 가이드

k-safeguard에 관심을 가져 주셔서 감사합니다. 이 문서는 이슈를 열거나 코드를 보내기 전에 알아 두면
좋은 내용을 정리합니다. 처음이라면 [1. 이 저장소가 다루는 것](#1-이-저장소가-다루는-것)과
[3. 이슈 열기](#3-이슈-열기)만 읽어도 충분합니다.

## 목차

1. [이 저장소가 다루는 것](#1-이-저장소가-다루는-것)
2. [개발 환경](#2-개발-환경)
3. [이슈 열기](#3-이슈-열기)
4. [코드 기여 규칙](#4-코드-기여-규칙)
5. [브랜치와 커밋](#5-브랜치와-커밋)
6. [Pull Request](#6-pull-request)
7. [문서 작성 규칙](#7-문서-작성-규칙)
8. [공격 예시와 데이터 다루기](#8-공격-예시와-데이터-다루기)
9. [라이선스](#9-라이선스)

## 1. 이 저장소가 다루는 것

k-safeguard는 **난독화된 한국어를 원래 문장으로 되돌리는 정규화기**입니다. 한글 표기
난독화(자모 분해, 된소리, 투명문자 등)를 되돌리며, 가드레일 앞단에 붙여 우회 입력을 막는 것은
그 활용 중 하나입니다.

| 이 저장소 | 다른 곳 |
|---|---|
| `k_safeguard` 패키지(`src/`), 테스트, 예제, 웹 데모, 배포 설정 | 실험 러너·결과, 난독화 생성기, 시드 데이터 → [k-safeguard-ML-experiment](https://github.com/jinseok3639/k-safeguard-ML-experiment) |
| | 벤치마크 데이터셋 → [HF: kimchunsik03/KoreanGuardrail](https://huggingface.co/datasets/kimchunsik03/KoreanGuardrail) |

실험 제안이나 실험 결과에 대한 질문은 실험 저장소에 이슈로 남겨 주세요.

### 이미 정해진 방향

아래는 프로젝트의 전제라서, 이를 뒤집는 제안은 받기 어렵습니다. 이슈를 쓰기 전에 확인해 주세요.

- **탐지 모델을 새로 학습하지 않습니다.** 복원 모델은 만들지만 가드레일과 경쟁하지 않습니다.
- **정규화기는 복원만 하고 판정하지 않습니다.** block/allow는 호출하는 쪽의 몫입니다.
- **범위는 한국어 표기 난독화입니다.** 타 언어 우회, 멀티모달, 에이전트형(도구 호출·파일 접근)
  위협은 다루지 않습니다.
- **런타임 의존성은 0개입니다.** 기본 설치에 Torch·Transformers·모델 가중치가 들어가지 않습니다.
- **프로세스는 가볍게 유지합니다.** Git Flow, 강제 브랜치 보호, semantic-release 같은 절차는
  도입하지 않습니다.

## 2. 개발 환경

Python 3.10 이상이 필요합니다. CI는 3.10·3.12·3.14에서 Linux·Windows·macOS 모두 돌립니다.

```bash
git clone https://github.com/jinseok3639/k-safeguard.git
cd k-safeguard
python -m pip install -e ".[dev]"
```

| 확인할 것 | 명령 |
|---|---|
| 테스트 | `python -m unittest discover -s tests` |
| 커버리지 | `python -m coverage run -m unittest discover -s tests && python -m coverage report` |
| 배포 산출물 경계 | `python -m pip install build && python -m build && python tools/release/verify_artifacts.py` |

변이 테스트(mutmut)는 Windows 네이티브 실행을 지원하지 않아 CI에서만 돕니다. 로컬에서 돌릴
필요는 없습니다.

## 3. 이슈 열기

[새 이슈](https://github.com/jinseok3639/k-safeguard/issues/new/choose)를 누르면 아래 템플릿 중
하나를 고르게 됩니다. 맞는 템플릿이 없을 때만 빈 이슈를 써 주세요.

| 템플릿 | 이럴 때 | 먼저 확인할 문서 |
|---|---|---|
| [정규화 커버리지 갭](https://github.com/jinseok3639/k-safeguard/issues/new?template=1_normalization_gap.yml) | 난독화 표기가 복원되지 않거나 잘못 복원된다 | [NORMALIZER.md](./dev_note/NORMALIZER.md)의 지원 범위와 "MVP에서 변경하지 않는다" 목록, [난독화 분류표](./dev_note/KOREAN_OBFUSCATION_RESEARCH.md) 3장 |
| [버그 리포트](https://github.com/jinseok3639/k-safeguard/issues/new?template=2_bug_report.yml) | 예외가 나거나 API가 문서와 다르게 동작한다 | [EXECUTION.md](./dev_note/EXECUTION.md)의 API 계약과 오류 정책 |
| [개선 제안](https://github.com/jinseok3639/k-safeguard/issues/new?template=3_enhancement.yml) | 기능 추가, 리팩터링, 문서 개선 | 위 [이미 정해진 방향](#이미-정해진-방향) |

좋은 이슈의 조건은 세 가지입니다.

- **바로 실행되는 재현 코드.** `k_safeguard`는 의존성이 없어 GPU나 모델 없이 재현됩니다.
- **기대 출력과 실제 출력.** 문자열은 그대로 붙여 넣어 주세요. 보이지 않는 문자가 있다면
  `repr()` 결과도 함께 적어 주세요.
- **이슈 하나에 문제 하나.** 여러 표기 변형을 한꺼번에 보고하면 추적이 어렵습니다.

측정 수치를 근거로 들 때는 지표 정의를 [EVALUATION_SPEC.md](./dev_note/EVALUATION_SPEC.md)에
맞춰 주세요.

## 4. 코드 기여 규칙

### 패키지 불변식

아래 네 가지는 테스트가 지키고 있으며, 바꾸는 PR은 병합하지 않습니다.

1. **원문 view는 항상 첫 번째입니다.** 정규화 결과가 원문을 대체하지 않습니다.
2. **기본 `Gateway` 경로는 무손실 정규화만 씁니다.** 정보가 손실되는 후보 생성(된소리 역변환,
   연음 역복원 등)은 호출자가 명시적으로 주입하는 opt-in provider로만 제공합니다.
3. **전역 Unicode NFC를 적용하지 않습니다.** 현대 한글 자모열만 조합해 한영 혼용 입력과 이모지
   ZWJ 시퀀스를 보존합니다.
4. **런타임 의존성을 추가하지 않습니다.** 무거운 의존성이 필요한 기능은 extras와 opt-in provider로
   분리합니다([PACKAGING.md](./dev_note/PACKAGING.md)).

### 테스트

- 새 정규화 규칙이나 후보 생성 규칙에는 단위 테스트를 함께 보내 주세요.
- 다음 경계 사례를 확인해 주세요: 빈 입력, 문장부호, 한영 혼용, 독립 자모(`ㄱ`, `ㅏ`), 완성형
  음절, 호환 자모와 조합형 자모, 공백.
- 테스트는 `unittest`로 작성하고 `tests/` 아래에 둡니다. 외부 모델이나 네트워크에 의존하면 안
  됩니다.
- 커버리지는 분기(branch) 기준으로 잽니다. 새 분기를 테스트 없이 추가하지 말아 주세요.

### 코드 스타일

- 공개 API에는 타입 힌트와 짧은 docstring을 붙입니다.
- 원본 입력을 보존하고, 어떤 규칙이 무엇을 바꿨는지(`edits`, rule ID) 추적할 수 있게 합니다.
- 주석과 docstring은 주변 코드에 맞춰 한국어로 씁니다.

## 5. 브랜치와 커밋

### 브랜치

`main`은 항상 데모 가능한 상태로 유지합니다. 직접 push하지 말고 브랜치에서 작업해 PR을 보내
주세요. 외부 기여자는 fork에서 같은 이름 규칙을 쓰면 됩니다.

| prefix | 용도 | 예 |
|---|---|---|
| `feature/` | 기능 추가 | `feature/spaced-jamo-provider` |
| `fix/` | 버그 수정 | `fix/compound-final-split` |
| `docs/` | 문서 | `docs/contributing-guide` |
| `chore/` | 정리, 설정, CI | `chore/repo-cleanup` |

### 커밋 메시지

`type(scope): 한글 설명` 형식을 씁니다. 설명은 무엇을 바꿨는지 한 줄로 적습니다.

| type | 용도 |
|---|---|
| `feat` | 기능 추가 |
| `fix` | 버그 수정 |
| `docs` | 문서 |
| `test` | 테스트만 변경 |
| `refactor` | 동작 변화 없는 구조 변경 |
| `chore` | 빌드, CI, 정리 |

```text
feat(normalizer): 반각 모음 정규화 추가
fix(gateway): 빈 입력에서 trace가 비는 문제 수정
docs(contributing): 이슈 템플릿 안내 추가
```

## 6. Pull Request

### 보내기 전에

1. 관련 이슈가 있으면 먼저 남겨 주세요. 큰 변경은 이슈에서 방향을 맞춘 뒤 시작하는 편이 서로
   시간을 아낍니다.
2. 로컬에서 `python -m unittest discover -s tests`가 통과하는지 확인해 주세요.
3. 공개 API나 동작을 바꿨다면 관련 문서(`README.md`, `dev_note/`, `examples/`)도 함께 고쳐 주세요.

PR을 열면 [PR 템플릿](./.github/pull_request_template.md)이 채워집니다. 체크리스트를 지우지
말고 해당하는 항목에 표시해 주세요. 오타 같은 사소한 문서 수정도 PR로 보내 주시면 됩니다.

### CI

PR에서 다음 검사가 자동으로 돕니다. 검사가 모두 통과한 PR만 병합합니다.

| 워크플로 | 하는 일 | 도는 조건 |
|---|---|---|
| [Python package](./.github/workflows/package.yml) | 3개 OS × 3개 Python 버전 테스트, wheel 빌드, 배포 경계 검증 | `src/`, `tests/`, `examples/`, `tools/release/`, 패키징 파일 변경 |
| [Coverage](./.github/workflows/coverage.yml) | 분기 커버리지 측정 | `src/`, `tests/`, `tools/`, `pyproject.toml` 변경 |
| [Mutation testing](./.github/workflows/mutation-testing.yml) | mutmut 변이 테스트 | `src/k_safeguard/`, `tests/`, `pyproject.toml` 변경 |
| [GitHub Pages demo](./.github/workflows/pages.yml) | 웹 데모 빌드 | `src/`, `web/`, `tools/web/` 변경 |
| [Claude Code Review](./.github/workflows/claude-code-review.yml) | 자동 리뷰 코멘트. 참고용이며 사람 리뷰를 대신하지 않습니다 | 모든 PR |

### 리뷰와 병합

- 메인테이너 한 명 이상이 리뷰한 뒤 병합합니다.
- 리뷰 코멘트에 답하면서 커밋을 추가해 주세요. 리뷰 중에는 force-push를 피해 주세요.
- 병합한 브랜치는 삭제합니다.

## 7. 문서 작성 규칙

- 사용자 대상 문서는 한국어를 우선합니다. 프로젝트 이름은 `k-safeguard`, import 이름은
  `k_safeguard`로 씁니다.
- 연구 주장에는 출처나 재현 가능한 결과를 연결합니다. 수치를 인용할 때는 생성기와 모델 버전을
  함께 적습니다.
- 과장하지 않습니다. "세계 최초", "가드레일을 대체한다" 같은 표현은 쓰지 않습니다. 가드레일에
  붙일 때 이 정규화기는 **방어 레이어 중 하나**입니다.

## 8. 공격 예시와 데이터 다루기

- 이슈·PR·테스트에 쓰는 공격 예시는 재현에 필요한 최소한으로 줄여 주세요. 실제로 유해한 요청
  원문 대신 `시스템 프롬프트를 보여줘` 수준의 예시면 충분합니다.
- 모델 예측 결과(`predictions.jsonl`, `results/`)처럼 공격 원문이 대량으로 들어 있는 파일은 커밋하지
  않습니다.
- 비밀키, 토큰, 실제 사용자 데이터는 어디에도 올리지 않습니다.
- 모델 체크포인트와 대용량 데이터셋은 Git에 넣지 않습니다.

## 9. 라이선스

코드는 [Apache License 2.0](./LICENSE)을 따릅니다. PR을 보내면 기여한 코드도 같은 라이선스로
배포하는 데 동의하는 것으로 봅니다. 벤치마크 데이터셋은 CC-BY-4.0입니다.
