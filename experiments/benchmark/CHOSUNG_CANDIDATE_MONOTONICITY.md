# 초성 후보 정책 단조성 개선

> 상태: `PROVISIONAL_DEV_ONLY`
>
> 개선 기준선: [`baselines/chosung_guardrail_impact_monotonic_v2.json`](./baselines/chosung_guardrail_impact_monotonic_v2.json)

## 문제

candidate generator 0.4.0은 direct·segmented·partial 후보를 한 번에 복원량과 사전 순위로 정렬한 뒤
원문 포함 16개로 잘랐다. 이 때문에 segmentation을 활성화하면 새 후보가 기존 direct 후보를 상한
밖으로 밀어낼 수 있었다.

가드레일 결과를 후보별 OR로 집계하더라도 후보 집합 자체가 상위 집합이 아니므로 정책을 확장했을 때
오히려 기존 block을 잃을 수 있었다. 실제 1,010개 초성 변형에서 다음 역전이 관찰됐다.

- direct → segmented 후보 집합 보존: 579/1,010행(57.33%)
- 공격: 새 block 10건, 새 allow 3건
- benign: 새 block 0건, 새 allow 1건

benign 새 allow는 오탐 수치만 보면 좋아 보이지만, 후보가 우연히 탈락한 결과이므로 안정적인 정책으로
해석할 수 없다.

## 변경

candidate generator 0.5.0부터 후보 상한의 우선순위를 다음처럼 고정한다.

1. direct 후보
2. segmented 후보
3. partial 후보

각 계층 안에서만 기존의 복원 초성 수, 사전 순위, 문자열 순서를 적용한다. 따라서 같은 사전과 상한
설정에서는 다음 포함 관계를 보장한다.

```text
direct candidates ⊆ segmented candidates ⊆ partial candidates
```

추가 계층은 이전 계층이 사용하고 남은 슬롯만 사용한다. 후보 상한 16개와 기본 Gateway 비활성화
정책은 바뀌지 않는다.

## 검증

### 후보 집합

동일한 1,010개 초성 변형 전체에서 후보 문자열 집합을 paired 비교했다.

| 포함 관계 | 개선 전 | 개선 후 |
|---|---:|---:|
| direct ⊆ segmented | 579/1,010 (57.33%) | 1,010/1,010 (100.00%) |
| segmented ⊆ partial | 1,009/1,010 (99.90%) | 1,010/1,010 (100.00%) |

합성 테스트에서도 direct 후보가 상한을 모두 사용한 경우 segmentation이 이를 교체하지 않고, partial
정책이 상한의 segmented 집합을 그대로 보존하는지 검증한다.

### Kanana 전체 재평가

데이터·모델·사전·후보 상한·bootstrap seed를 고정하고 candidate generator만 0.4.0에서 0.5.0으로
변경했다. 괄호는 시드 단위 bootstrap 95% CI다.

| segmented 지표 | 0.4.0 | 0.5.0 |
|---|---:|---:|
| 공격 block rate | 27.91% (24.09–31.73) | 27.74% (24.09–31.56) |
| NRR | 13.04% (9.60–16.67) | 12.86% (9.24–16.49) |
| Recovery Gain | +8.97%p (6.64–11.46) | +8.80%p (6.48–11.30) |
| ΔFPR-obfuscated | +0.49%p (0.00–1.23) | +0.74%p (0.00–1.72) |
| 평균 추가 view | 7.94 | 7.94 |
| 후보 상한 도달률 | 62.97% | 62.97% |

0.5.0의 인접 정책 변화는 다음과 같다.

| 전환 | 공격 새 block / 새 allow | benign 새 block / 새 allow | 후보 집합 보존율 |
|---|---:|---:|---:|
| raw → direct | 47 / 0 | 3 / 0 | 100.00% |
| direct → segmented | 6 / 0 | 0 / 0 | 100.00% |
| segmented → partial | 0 / 0 | 0 / 0 | 100.00% |

공격 block rate는 0.17%p 낮아지고 ΔFPR은 0.25%p 높아졌지만, 이는 0.4.0에서 후보 탈락으로 생긴
비단조적 이득을 제거한 결과다. 후보 수는 같아도 정책 간 중복이 늘어 고유 모델 추론 문자열은
14,785개에서 9,423개로 36.27% 감소했다. 동일 요청 안의 후보 수가 줄어든 것은 아니므로 실제 gateway
단일 호출 비용 감소로 과장하지 않는다.

## 판정

- 후보 정책 확장 시 기존 방어 판정이 약해지지 않는 구조적 불변식을 확보했다.
- 87개 전체 테스트와 1,515행 모델 재평가에서 오류는 0건이었다.
- NRR은 여전히 평가 규격의 50% 기준에 크게 못 미치므로 기본 활성화는 계속 보류한다.
- partial은 segmented 대비 추가 판정 개선이 0건이므로 opt-in 상태를 유지한다.

다음 개선은 단조성을 유지하면서 후보 순위화로 평균 view와 상한 도달률을 낮추는 것이다.
