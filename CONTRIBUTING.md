# 기여 가이드

2인 팀 연구형 프로젝트라 CLA·행동강령 같은 절차는 두지 않는다. 아래는 작업을 시작하는 데
필요한 최소한이다. 브랜치·커밋 컨벤션과 프로젝트 배경은 [AGENTS.md](./AGENTS.md)를 정본으로 한다.

## 개발 환경

```bash
python -m pip install -e ".[dev]"
python -m unittest discover -s tests
python -m coverage run -m unittest discover -s tests && python -m coverage report
```

모델 추론이 필요한 실험 코드(`experiments/`)는 별도 환경이 필요하다.
[`experiments/guardrail/README.md`](./experiments/guardrail/README.md)를 참고한다.

## 이슈로 보고하기

이슈를 열 때는 아래 세 템플릿 중 하나를 고른다. `Blank issue`도 허용하지만, 셋 중 하나에
맞으면 해당 템플릿을 쓰는 편이 처리가 빠르다.

| 템플릿 | 용도 |
|---|---|
| 정규화 커버리지 갭 | 정규화기가 못 되돌리거나 잘못 되돌리는 표기 변형 보고 |
| 버그 리포트 | 예외, API 오동작, 평가 스크립트 실패 |
| 개선 제안 | 기능 추가, 리팩터링, 문서 수정, 실험 항목 제안 |

정규화 커버리지 갭을 보고하기 전에는 [NORMALIZER.md](./dev_note/NORMALIZER.md)의 지원 범위와
"MVP에서 변경하지 않는다" 목록을 먼저 확인한다.

## PR 규칙

- 기능·실험 단위로 브랜치를 나누고 PR을 연다. 브랜치 prefix(`feature/`, `experiment/`,
  `fix/`, `docs/`)와 커밋 형식(`type(scope): 한글 설명`)은 [AGENTS.md의 Git
  워크플로](./AGENTS.md#git-워크플로)를 따른다.
- 오타·사소한 문서 수정은 PR 없이 바로 커밋해도 된다.
- 실험 PR 설명에는 결과 요약을 남긴다 — 보고서·대회 심사 근거로 재사용한다.
- 병합 전 `python -m unittest discover -s tests`가 통과해야 한다.
