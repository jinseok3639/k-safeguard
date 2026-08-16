# 로컬 가드레일 실험 환경

이 디렉터리는 `EVALUATION_SPEC.md`의 가드레일 모델을 Windows 로컬 GPU에서 재현하기 위한
격리 환경이다. ComfyUI의 내장 Python과 Ollama 저장소는 수정하지 않는다.

## 구성 원칙

- Python 환경: 저장소 루트의 `.venv-experiment`
- 모델 가중치: `D:\local llm\guardrails\models`
- Hugging Face 상태·캐시: `D:\local llm\guardrails\hf-home`
- CPU offload: `D:\local llm\guardrails\offload`
- 모델 ID와 revision: `models.json`
- 실제 설치 결과: `D:\local llm\guardrails\models.lock.json`

가중치와 로컬 환경은 Git에 커밋하지 않는다. 실험 결과는 model ID뿐 아니라 lock 파일의
`resolved_revision`, dtype, device map을 run manifest에 복사해야 한다.

## 선정 모델

| key | 역할 | 크기 | 기본 설치 | 비고 |
|---|---|---:|---|---|
| `kanana-content-8b` | 트랙 C 고정 모델 | 약 15.0 GiB | 예 | 한국어 콘텐츠 안전성, Apache-2.0 |
| `kanana-prompt-2.1b` | 트랙 P 고정 모델 | 약 3.9 GiB | 예 | 한국어 프롬프트 공격, Apache-2.0 |
| `qwen3guard-gen-0.6b` | 일반성 비교 | 약 1.4 GiB | 예 | 119개 언어·방언 지원, Apache-2.0 |
| `llama-prompt-guard-2-86m` | 경량 비교 | 약 1.1 GiB | 아니요 | 수동 약관 승인과 HF 로그인이 필요 |
| `wolf-defender-prompt-injection` | A1/A2 탐색 비교 | 약 1.8 GiB | 아니요 | 공개·비게이트, 한국어 OOD |

Kanana 두 모델은 `EVALUATION_SPEC.md`의 v0.1 revision을 그대로 사용한다. Qwen3Guard는 한국어를
별도로 성능 보증한 모델로 간주하지 않고, 공식 카드가 밝힌 다국어 지원 범위에 근거한 비교군으로만
사용한다. Prompt Guard 2의 공식 평가 언어 목록에는 한국어가 없으므로 설치하더라도 외삽
baseline으로 표시한다.
Wolf Defender는 prompt injection 전용 비교군이지만 한국어 성능을 보증하지 않는다. Transformers
5.x로 저장된 tokenizer 이름은 실험 환경 4.51.3에서 동일 `tokenizer.json`을 직접 읽는 호환 adapter로
처리하며 파일 해시를 결과에 남긴다.

## 설치

PowerShell에서 저장소 루트를 기준으로 실행한다.

```powershell
.\experiments\guardrail\setup.ps1
```

이 PC의 RTX 5070 Ti는 Blackwell 계열이므로 현재 공식 PyTorch CUDA 13.0 wheel을 설치한다.
스크립트는 `torch==2.13.0`, `transformers==4.51.3`과 나머지 의존성을 고정한다. Kanana 모델
카드의 최소 요구 버전이 4.51.3이며, 2026-08-05 현재 Transformers 5.14.1은 Kanana 2.1B의
GQA 설정을 strict validation에서 거부하므로 사용하지 않는다.

환경을 다시 사용할 때는 스크립트를 dot-source한다.

```powershell
. .\experiments\guardrail\enter-env.ps1
```

기본 활성화는 재현성을 위해 Hugging Face와 Transformers를 offline 모드로 둔다. 모델을 추가로
다운로드해야 하는 세션만 `-Online`을 사용한다.

```powershell
. .\experiments\guardrail\enter-env.ps1 -Online
```

## 모델 다운로드

기본 세 모델을 exact revision으로 받는다.

```powershell
python .\experiments\guardrail\download_models.py
```

예상 다운로드는 약 20.3 GiB다. 특정 모델만 받으려면 key를 지정한다.

```powershell
python .\experiments\guardrail\download_models.py --model kanana-prompt-2.1b
python .\experiments\guardrail\download_models.py --model wolf-defender-prompt-injection
```

Prompt Guard 2를 받으려면 먼저 모델 페이지에서 약관을 승인하고 Hugging Face CLI에 로그인한 뒤
선택 설치한다.

```powershell
hf auth login
python .\experiments\guardrail\download_models.py --model llama-prompt-guard-2-86m
```

토큰은 사용자 Hugging Face credential store에만 두며 저장소나 스크립트 인자에 기록하지 않는다.

## Smoke test

외부 네트워크 없이 로컬 파일만 읽고, 무해한 한국어 문장으로 출력 형식을 확인한다.

```powershell
python .\experiments\guardrail\smoke_test.py kanana-prompt-2.1b
python .\experiments\guardrail\smoke_test.py qwen3guard-gen-0.6b
python .\experiments\guardrail\smoke_test.py kanana-content-8b
python .\experiments\guardrail\smoke_test.py wolf-defender-prompt-injection
```

Kanana 8B의 BF16 가중치는 16GB VRAM에 여유 있게 전부 올라가지 않으므로 기본적으로 GPU를
13 GiB까지만 사용하고 나머지를 RAM으로 offload한다. 이는 환경 검증용 설정이다. 본 실험에서는
실제 device map과 지연시간을 run manifest에 남기고, 양자화를 도입하면 별도 run ID로 분리한다.

이 PC에서 확인한 설치 revision과 smoke test 결과는 [VERIFICATION.md](./VERIFICATION.md)에 남겼다.

## Gateway 연결 확인

`KananaPromptAdapter`는 `Gateway.evaluate()`의 callable 계약을 구현한다. 따라서 모델별 출력 해석,
원문·정규화 view 실행, OR 집계와 오류 정책을 한 경로에서 확인할 수 있다.

```powershell
. .\experiments\guardrail\enter-env.ps1
python -m experiments.guardrail.run_gateway "주말에 읽을 만한 한국 소설을 추천해 줘."
```

자모가 분리된 입력은 원문과 무손실 정규화문을 별도 view로 평가한다. 첫 block 뒤에도 전체 trace가
필요하면 `--all-views`를 사용한다.

```powershell
python -m experiments.guardrail.run_gateway "ㅇㅏㄴㄴㅕㅇ" --all-views
```

출력 JSON에는 최종 `block`, `category`, 최초 trigger와 각 view의 모델 revision, token hash,
모델·전체 호출 지연시간이 포함된다. classifier 장애를 차단으로 취급하려면
`--error-mode block`을 명시한다. CLI 종료 코드는 허용 0, 차단 1, classifier 오류 2다.

이 adapter는 로컬 실험·재현을 위한 것으로 wheel에 Torch나 Transformers 의존성을 추가하지 않는다.
일반 사용자는 자신의 모델 또는 API 호출부를 동일한 callable 계약으로 연결할 수 있다.

`KananaPromptAdapter.batch`는 `Gateway.evaluate_batch()`의 callable 계약을 구현한다. 여러 candidate
view를 왼쪽 padding한 뒤 한 번의 `generate()`로 판정하며, 실제 단일 호출 대비 판정 일치성과
처리량·VRAM 비교는 [batch 추론 진단](../benchmark/KANANA_BATCH_BENCHMARK.md)에 기록했다.

## 재현성 체크

- `models.json`의 revision을 임의로 `main`으로 바꾸지 않는다.
- Kanana는 공식 chat template과 첫 번째 새 토큰 판정을 사용한다.
- smoke test 성공은 모델 성능 검증이 아니라 설치·CUDA·출력 계약 확인이다.
- 비교 모델의 라벨과 threshold를 Kanana 형식으로 억지로 바꾸지 않는다.
- 실제 공격 데이터는 모델 설치나 smoke test에 사용하지 않는다.
