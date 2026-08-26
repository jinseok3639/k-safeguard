# 자모 슬롯 복원 후보 진단

> 기준선: [`baselines/ml_restore_v1.json`](./baselines/ml_restore_v1.json)
>
> 가중치 run ID: `proto-20260826b`
>
> 상태: `PROVISIONAL_DEV_ONLY`

## 목적

[`MlRestoreProvider`](../../src/k_safeguard/providers/ml_restore.py)가 내는 **단일 후보**가
얼마나 맞는지, 정상 입력을 얼마나 건드리는지 문자열 수준에서 잰다. 가드레일 추론은 하지
않으므로 여기 수치는 NRR·ΔFPR이 아니라 그 **proxy**다. 실제 모델 결과는
[자모 슬롯 복원 Kanana 평가](./ML_RESTORE_GUARDRAIL_IMPACT.md)에 기록한다.

[된소리 역변형 후보 진단](./TENSIFY_CANDIDATES.md)과 같은 층위지만 재는 것이 다르다.
`TensifyInverseProvider`는 후보를 최대 9개 나열하므로 **정답이 그 안에 있는가**(oracle
recall)를 재고, `MlRestoreProvider`는 후보가 하나뿐이라 **그 하나가 맞는가**를 잰다.
후자가 훨씬 엄격한 기준이며, 두 수치를 직접 비교하면 안 된다.

## 고정 설정

| 항목 | 값 |
|---|---|
| 데이터 | `hf_repo/benchmark.jsonl` — clean 505행 + tensify 1,010행 |
| 독립 시드 | 505 (attack 301, benign hard-negative 204) |
| 복원기 | 자모 MLP 3종 (`tensify`, `liaison`, `jongseong_cram`), 파라미터 각 28만 |
| 임계값 | `tensify` 0.999999 · `liaison` 0.99 · `jongseong_cram` 0.99 |
| 추론 | onnxruntime CPU, batch 없음 |
| 가드레일 | **사용하지 않음** |

## 결과

`후보`는 provider가 후보를 낸 비율, `exact`는 손상된 행 중 원문과 완전히 같아진 비율이다.

| technique | intensity | label | n | 후보 | exact | raw CER | residual CER | CER 감소 |
|---|---|---|---:|---:|---:|---:|---:|---:|
| clean | 0 | attack | 301 | 4.65% | - | - | - | - |
| clean | 0 | benign | 204 | **0.98%** | - | - | - | - |
| tensify | 0.5 | attack | 301 | 83.72% | 3.00% | 15.42% | 10.47% | +4.94%p |
| tensify | 0.5 | benign | 204 | 83.82% | 9.80% | 13.38% | 7.98% | +5.40%p |
| tensify | 1.0 | attack | 301 | 98.67% | 0.67% | 31.08% | 18.21% | **+12.88%p** |
| tensify | 1.0 | benign | 204 | 99.51% | 0.00% | 26.67% | 16.21% | +10.45%p |

## 해석

### 세 모델을 함께 켜면 정상 입력 비용이 두 배가 된다

기법 하나씩 따로 재면 정상 입력 오변경은 `tensify` 0.49%(1/204), `liaison` 0.49%,
`jongseong_cram` 0.00%다. 그런데 provider는 세 모델을 순서대로 돌려 **먼저 후보를 내는
쪽**을 쓰므로, 각 모델이 각자 발동할 기회를 갖는다. 그 결과가 위 표의 0.98%(2/204)다.

승격 기준 ≤1%를 형식상 넘지만 **여유가 사실상 없다.** 문장 하나가 곧 0.49%p이므로
benign 204개로는 0.98%와 1.5%를 구별할 수 없다. 기법을 더 붙이면 이 값은 더 오른다 —
provider에 모델을 추가할 때는 이 합산 비용을 다시 재야 한다.

### exact는 무너지지만 CER 감소는 남는다

`tensify` intensity 1.0에서 완전 복원은 0.67%인데 CER은 12.88%p 줄어든다. 임계값
0.999999가 확신 있는 자리만 고치고 나머지는 그대로 두기 때문이다 — 부분 복원이
대부분이다. 가드레일 판정을 뒤집는 데 완전 복원이 필요한지 부분 복원으로 충분한지는
문자열 수준에서 답할 수 없고, 실제 모델 평가가 필요하다.

### 정상 입력에도 CER 감소가 나타나는 것은 정상이다

`tensify` benign 행은 정상 문장을 인위적으로 된소리화한 hard-negative이므로, 되돌리면
원문에 가까워지는 것이 맞다. 이 행의 CER 감소는 복원 성능이지 오탐이 아니다. 오탐에
해당하는 것은 `technique=clean` 행의 후보 발생률이다.

## 재현

가중치는 패키지에 들어 있지 않다. 샌드박스에서 만들어 경로를 넘긴다.

```powershell
python -m experiments.benchmark.run_ml_restore_evaluation `
  --weights <가중치 디렉터리>
```

가중치 디렉터리에는 `manifest.json`과 기법별 `<technique>.onnx`·`<technique>.vocab.json`이
있어야 하며, 재생성 명령은 manifest의 `provenance.regenerate_with`에 기록된다.

## 해석 경계

- 가드레일 추론이 없다. 여기 수치는 ΔFPR의 proxy이며 NRR이 아니다.
- `liaison`과 `jongseong_cram`은 `hf_repo/benchmark.jsonl`에 해당 난독화 행이 없어
  **여기서 평가되지 않았다.** 두 모델은 정상 입력 비용에만 기여한다(위 0.98%).
  기법별 수치는 baseline의 `scope.not_evaluated`에 명시했다.
- benchmark의 `tensify` 생성기는 문맥과 무관하게 초성을 경음으로 바꾸며, 복원기 학습에
  쓴 생성기와 구현이 다르다. 두 분포가 완전히 같지 않다.
- 단일 실행이며 seed 단위 bootstrap CI를 계산하지 않았다.
