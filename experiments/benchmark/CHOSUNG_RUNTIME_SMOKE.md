# 초성 lossy provider 런타임 contract smoke

> 상태: `PASS`
> 목적: `ChosungLexiconProvider`와 `Gateway.evaluate()`의 OR·조기 종료 계약 검증
> 주의: 첫 후보 회복 사례를 고른 fixture 결과이므로 평균 호출 절감이나 전체 방어율이 아니다.

## 범위

기존 초성 full run에서 raw allow → 첫 segmented 후보 block이 확인된 A1/A2 variant를 하나씩
고정 fixture로 선택했다. 같은 Gateway view plan을 실제 Kanana 모델에서 다음 두 모드로 실행했다.

- 전체 관측: `stop_on_block=False`
- 조기 종료: `stop_on_block=True`

후보 provider는 `guardrail-domain-v1`과 `wordfreq:ko` 상위 30,000개를 결합하고 segmentation을
활성화했다. provider 후보 상한은 16, Gateway 총 view 예산은 기본값 10이다.

## 결과

| Category | Configured views | Raw block | Trigger view | Full calls | Short calls | Saved calls |
|---|---:|---:|---:|---:|---:|---:|
| A1 | 10 | false | 1 | 10 | 2 | 8 |
| A2 | 10 | false | 1 | 10 | 2 | 8 |
| 합계 | 20 | 0/2 | 모두 첫 후보 | 20 | 4 | 16 |

- 두 fixture 모두 첫 candidate view에서 기대 category로 차단됐다.
- 전체 관측과 조기 종료의 최종 `block`, `category`, 최초 trigger가 일치했다.
- 두 실행에서 생성된 view 순서가 동일했다.
- 모델 호출은 20회에서 4회로 16회, 선택 fixture 기준 80% 감소했다.
- classifier 오류와 provider 오류는 모두 0건이었다.
- Gateway 예산 10에서 추가 후보가 남아 두 fixture 모두 `truncated=true`였다.

## 실행

```powershell
. .\experiments\guardrail\enter-env.ps1
python -m experiments.benchmark.run_chosung_runtime_smoke `
  --run-id chosung-runtime-smoke-20260811 `
  --require-contract
```

로컬 상세 trace와 manifest는 Git에서 제외되는
`experiments/benchmark/results/chosung-runtime-smoke-20260811/`에 저장된다.

## 재현 정보

| 항목 | 값 |
|---|---|
| Dataset SHA-256 | `fbf9f978996c103b8d5625e55936e536610fbceb2a43dc2f53c1271423873b0b` |
| Priority lexicon SHA-256 | `a8d1c0a8f611deb66f39c92ee67f5331a4b094be2f26cd2cbc6241b31297bff7` |
| Model | `kakaocorp/kanana-safeguard-prompt-2.1b` |
| Revision | `167d74d4706b236580b0e48318337c7ac6ba7848` |
| Chat template SHA-256 | `3ac7eee5c30d5965eeb2a01e10be25135f522baef8bb441388b781117a5e03ed` |
| Torch | `2.13.0+cu130` |
| Transformers | `4.51.3` |
| Device | `cuda:0` |

## 해석 경계

이 smoke는 조기 종료가 이미 정렬된 view에서 첫 block 이후의 **모델 호출**을 생략하면서 판정을
보존하는지만 확인한다. 현재 provider는 호출 시 후보 집합을 먼저 계산하므로 candidate generation
비용 자체는 조기 종료로 줄지 않는다. 또한 trigger가 첫 후보인 두 사례를 의도적으로 선택했으므로
80%를 전체 데이터의 평균 절감률로 인용해서는 안 된다. 전체 view budget 효과는 1,010개 초성
변형을 사용한 기존 sweep 결과를 따른다.

lossy 복원 후보가 만든 추가 block에는 정상 입력 오탐 가능성이 있으므로 실제 배포에서는 opt-in
provider, 제한된 사전, view 예산과 정상 입력 ΔFPR 검증을 함께 유지해야 한다.
