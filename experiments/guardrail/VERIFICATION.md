# 로컬 설치 검증 기록

> 검증일: 2026-08-05
>
> 범위: 설치·CUDA·로컬 로드·출력 계약 smoke test
>
> 주의: 이 결과는 모델 정확도나 난독화 방어율 측정 결과가 아니다.

## 환경

| 항목 | 값 |
|---|---|
| GPU | NVIDIA GeForce RTX 5070 Ti, 16,303 MiB |
| NVIDIA driver | 591.86 |
| 시스템 RAM | 31.1 GiB |
| Python | 3.10.0, `.venv-experiment` |
| PyTorch | 2.13.0+cu130 |
| Transformers | 4.51.3 |
| Hugging Face Hub | 0.36.0 |
| 모델 루트 | `D:\local llm\guardrails` |

Transformers 5.14.1도 먼저 확인했으나 Kanana 2.1B의 GQA configuration을 strict validation에서
거부했다. Kanana 모델 카드의 공식 최소 요구 버전인 4.51.3으로 고정한 뒤 세 모델 모두 로드됐다.

## 설치 결과

| key | resolved revision | 디스크 | 상태 |
|---|---|---:|---|
| `kanana-content-8b` | `2f4a68641d818caf873e21badcdc161928b0fcbf` | 14.97 GiB | 설치 완료 |
| `kanana-prompt-2.1b` | `167d74d4706b236580b0e48318337c7ac6ba7848` | 3.90 GiB | 설치 완료 |
| `qwen3guard-gen-0.6b` | `fada3b2f655b89601929198343c94cd2f64d93cc` | 1.41 GiB | 설치 완료 |
| `llama-prompt-guard-2-86m` | `a8ded8e697ce7c355e395a0df51f94adb4a2fd27` | - | 약관 접근 권한이 없어 미설치 |

실제 설치 상태의 정본은 Git 외부의 `D:\local llm\guardrails\models.lock.json`이다.

## Offline smoke test

무해 입력 `주말에 읽을 만한 한국 소설을 추천해 줘.`를 사용했다.

| key | raw output | 출력 계약 | 로드 포함 시간 |
|---|---|---|---:|
| `kanana-prompt-2.1b` | `<SAFE>` | 통과 | 3.54초 |
| `qwen3guard-gen-0.6b` | `Safety: Safe` / `Categories: None` | 통과 | 2.35초 |
| `kanana-content-8b` | `<SAFE>` | 통과 | 23.85초 |

Kanana 8B는 GPU 가중치 예산을 13 GiB로 제한하고 나머지를 CPU RAM으로 offload했다. 위 시간은
단일 cold-start 관측치이므로 성능 benchmark로 사용하지 않는다.

## 추가 검사

- `pip check`: broken requirement 없음
- Python 두 스크립트 `py_compile`: 통과
- PowerShell 설치·활성화 스크립트 parser 검사: 통과
- 모델 다운로드 dry-run의 디스크 여유 검사: 통과
- 세 smoke test 모두 `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`에서 통과

## 추가 설치 검증 (2026-08-14)

08-05 검증 이후 `wolf-defender-prompt-injection`을 추가 설치했다. 별도 offline smoke test 기록은
없지만, [Wolf Defender 된소리 교차 검증](../benchmark/TENSIFY_WOLF_CROSS_MODEL_RESULT.md)에서
실행 오류 0건·provider 오류 0건으로 336개 레코드를 실제 추론했으므로 설치·로드가 정상 동작함을
간접 확인했다.

| key | resolved revision | 디스크 | 상태 |
|---|---|---:|---|
| `wolf-defender-prompt-injection` | `ecc382bd4d98ffa19e1c9c2ce4a0722904c04a3c` | 약 1.8 GiB | 설치 완료 |
