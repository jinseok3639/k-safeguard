# Wolf Defender 된소리 교차 모델 검증 결과

> 실행 ID: `tensify-wolf-cross-model-v1-20260814`
>
> 사전등록 commit: `f698dac`
>
> 판정: `VALID_OOD_REPLICATION`

## 결론

A1/A2 전용 분류기에서 역정규화의 공격 복구 효과는 재현됐지만 오탐 비용도 컸다. `ratio_0.10`은
난독화 공격 차단을 20/28(71.43%)에서 27/28(96.43%)로 25.00%p 높였다. 동시에 난독화 정상문
오탐은 4/28(14.29%)에서 10/28(35.71%)로 21.43%p 높였다. clean 입력 오탐은 늘지 않았다.

원문에서 차단되다가 난독화 후 허용된 공격은 2개였고 둘 다 복구해 NRR은 2/2(100%)다. 표본이
작고 모델의 한국어 범위가 OOD이므로 이 수치만으로 일반 성능을 주장하지 않는다. 현재
`DO_NOT_PROMOTE` 결정과 `ratio_0.10` threshold를 유지한다.

## 핵심 수치

| 지표 | `ratio_0.10` | `all` | 해석 |
|---|---:|---:|---|
| 원문 공격 차단 | 20/28 (71.43%) | 동일 | 사전등록 coverage 최소값 통과 |
| raw CER | 2/20 (10.00%) | 동일 | clean 차단 공격 cohort |
| NRR | 2/2 (100%) | 2/2 (100%) | 표본 2 |
| 공격 recovery gain | +7/28 (+25.00%p) | 동일 | 난독화 공격 27/28 차단 |
| raw clean FPR | 3/28 (10.71%) | 동일 | 원문 오탐 |
| ΔFPR-clean | 0/28 (0.00%p) | +1/28 (+3.57%p) | ratio가 clean 신규 오탐 억제 |
| raw obfuscated FPR | 4/28 (14.29%) | 동일 | 난독화 원문 오탐 |
| ΔFPR-obfuscated | +6/28 (+21.43%p) | 동일 | 가장 큰 승격 저해 요인 |
| clean activation | 1/56 (1.79%) | 27/56 (48.21%) | ratio의 비용 우위 |
| obfuscated activation | 56/56 (100%) | 동일 | 후보 상한 근접 |

bootstrap 95% CI와 subgroup 전체는 frozen baseline에 보존했다. `ratio_0.10`의 recovery gain CI는
10.71~42.86%p, ΔFPR-obfuscated CI는 7.14~39.29%p다.

## 재현성과 제한

- 실행 오류 0, provider 오류 0, 336 records
- 고유 모델 입력 565개, batch 18회, 추론 0.625초, 904.0 views/s
- 모델 revision과 FP32 argmax 라벨 규칙을 실행 전에 봉인
- 공개 카드상 한국어 학습·평가 미명시: 한국어 OOD 결과
- 공개 학습 소스 목록은 있으나 exact-text 중복 감사 불가
- 동일 데이터에서 threshold·라벨 규칙 재조정 및 재실행 없음

정본은 `baselines/tensify_wolf_cross_model_v1.json`, 실행 전 seal은
`baselines/tensify_wolf_cross_model_seal_v1.json`이다.

## 다음 결정

된소리 역정규화의 공격 회복 자체는 두 비교 모델에서 관측됐지만, Wolf에서는 난독화 정상문 오탐이
크게 증가했다. 다음 개선은 threshold 재튜닝이 아니라 후보별 OR 차단 전에 신뢰도·문맥을 이용해
무해 후보를 거르는 **label-free 후보 선택 규칙**을 dev set에서 설계하는 것이다. 새 규칙은 별도
사전등록과 새 test set 없이는 승격하지 않는다.

