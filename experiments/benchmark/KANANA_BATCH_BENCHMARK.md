# Kanana Prompt batch 추론 진단

## 결론

Kanana Safeguard-Prompt 2.1B에서 동일한 20개 Gateway view를 단일 호출과 batch size 2·4·10으로
각 7회 비교했다. 모든 batch 조건에서 최종 판정, view별 block/category/error, 생성 token ID와
tokenized input hash가 단일 호출 기준선과 완전히 일치했고 classifier 오류는 없었다.

RTX 5070 Ti 16GB 환경의 중앙값 기준으로 batch size 10은 모델 호출을 20회에서 2회로 줄이고,
wall time을 514.2ms에서 132.1ms로 낮췄다. 처리량은 38.9에서 151.4 views/s로 증가했다. 대신
추론 중 추가 peak allocated VRAM은 19.8MiB에서 230.3MiB로 증가했다.

| mode | 모델 호출 | 호출 감소 | wall 중앙값 | wall 감소 | 처리량 중앙값 | speedup | 추가 peak allocated VRAM |
|---|---:|---:|---:|---:|---:|---:|---:|
| single | 20 | 기준 | 514.157ms | 기준 | 38.899 views/s | 1.000x | 19.835MiB |
| batch 2 | 10 | 50% | 266.006ms | 48.3% | 75.186 views/s | 1.933x | 40.335MiB |
| batch 4 | 6 | 70% | 180.229ms | 64.9% | 110.970 views/s | 2.853x | 79.967MiB |
| batch 10 | 2 | 90% | 132.080ms | 74.3% | 151.424 views/s | 3.893x | 230.299MiB |

## 측정 규격

- run ID: `kanana-batch-runtime-20260811`
- 코드 commit: `5c262d03d87105781ffe88976f6edc933068a272`
- 모델: `kakaocorp/kanana-safeguard-prompt-2.1b`
- model revision: `167d74d4706b236580b0e48318337c7ac6ba7848`
- dtype: float16
- GPU: NVIDIA GeForce RTX 5070 Ti 16GB
- Torch/CUDA: 2.13.0+cu130 / CUDA 13.0
- Transformers: 4.51.3
- 입력: 기존 초성 runtime smoke의 고정 A1/A2 fixture 2개
- view 계획: fixture당 10개, 총 20개
- 조건: single, batch 2, batch 4, batch 10
- 반복: 조건별 7회, 사전 warmup 1회
- 순서 효과 완화: 반복마다 조건 실행 순서를 회전
- 집계: wall time, views/s와 추가 peak allocated VRAM의 중앙값
- Gateway 정책: `stop_on_block=False`, `error_mode="allow"`

`stop_on_block=False`는 네 조건이 같은 20개 view를 실제로 판정하게 만들기 위한 선택이다. 따라서 이
실험은 조기 종료 효과가 아니라 classifier batching 효과만 비교한다. CUDA 메모리는 각 조건 직전
cache 정리와 동기화 후 `reset_peak_memory_stats()`를 호출하고, 모델 상주 baseline을 뺀 peak allocated
증분을 기록했다.

원시 반복의 wall time 범위도 좁았다.

| mode | 최소 | 최대 |
|---|---:|---:|
| single | 511.926ms | 520.852ms |
| batch 2 | 265.205ms | 274.861ms |
| batch 4 | 177.689ms | 183.020ms |
| batch 10 | 130.934ms | 132.260ms |

## 구현 판단

- 이 GPU와 2.1B 모델에서 처리량 우선이면 `batch_size=10`이 가장 유리했다. Gateway의 현재 최대 view
  예산 10개를 fixture당 한 번에 처리하면서 추가 peak allocated VRAM은 약 230MiB였다.
- 더 보수적인 메모리 설정이 필요하면 `batch_size=4`가 80MiB 미만의 추가 peak allocated VRAM으로
  2.85배 speedup을 보였다.
- core 라이브러리의 보편적 batch size로 특정 값을 강제하지 않는다. 모델 크기, prompt 길이, GPU,
  원격 API 제한에 따라 메모리와 처리량 곡선이 달라지므로 사용자가 `batch_size`를 정해야 한다.
- Kanana 실험 adapter는 causal LM batch generation에 필요한 왼쪽 padding을 사용한다. attention mask로
  padding을 제외한 원래 token ID를 복원해 기존 token count와 hash 추적성을 유지한다.

## 해석 경계

이 결과는 한 PC, 한 모델, 고정 fixture 두 개의 runtime 진단이다. 모집단 안전 성능, 실제 서비스의
동시 요청 처리량이나 모든 prompt 길이에 대한 메모리 안전성을 추정하지 않는다. 실제 배포 전에는
서비스의 최대 입력 길이와 동시성 조건으로 batch size를 다시 측정해야 한다.

또한 batch는 chunk 전체를 이미 모델에 전달하므로 chunk 안에서 block이 발견되어도 그 chunk의 모든
결과가 계산된다. 보안 판정은 단일 호출과 같지만, 조기 종료 절감과 batch 처리량 사이의 균형은
`batch_size`로 조절한다.

## 재현

모델과 `.venv-experiment` 환경을 준비한 뒤 저장소 루트에서 실행한다.

```powershell
.\.venv-experiment\Scripts\python `
  -m experiments.benchmark.run_kanana_batch_benchmark `
  --run-id <unique-run-id> `
  --repeats 7 `
  --warmup-rounds 1 `
  --require-parity
```

결과의 `manifest.json`은 모델·revision·런타임·데이터 hash·view 수·측정 설정을 기록한다.
`measurements.jsonl`은 조건별 원시 반복값, `summary.json`과 `report.md`는 중앙값 요약을 저장한다.
실험 결과 폴더에는 평가 입력에서 파생된 정보가 포함될 수 있어 Git에는 추가하지 않는다.
