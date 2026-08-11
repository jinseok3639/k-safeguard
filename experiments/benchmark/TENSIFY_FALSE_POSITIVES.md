# 된소리 benign dev raw 오탐 분석

## 결론

64개 사람 검수 전 dev 문장에서 raw Kanana의 오탐은 9건(14.06%)이었다. 그중 8건이
`technical_meta`, 1건이 `mixed_format`이었다. `all`과 `ratio_0.10`도 같은 9건을 block했고,
두 정책 모두 raw 대비 새 block·새 allow가 0건이었다. 모든 오탐의 trigger view가 원문인 index 0이므로
이 결과에서는 후보 생성기가 오탐을 추가했다는 증거가 없다.

| 구분 | 결과 |
|---|---:|
| raw FPR | 9/64 (14.06%) |
| raw category | A1 5건, A2 4건 |
| technical_meta | 8/16 (50.00%) |
| mixed_format | 1/16 (6.25%) |
| colloquial_chat / everyday_lexical | 각 0/16 |
| `all` / `ratio_0.10`의 raw 대비 판정 전환 | 각 0/64 |

오탐 9건 중 보안 관련 어휘가 포함된 문장은 6건, 명령·실행·절차 어휘 3건, 모델·프롬프트 어휘
3건, 안전·개인정보·권한 어휘 3건이었다. 이는 단순 동시 출현 집계이며 특정 단어나 조합이 모델의
인과적 trigger라는 뜻은 아니다. 특히 `tb053`은 이 어휘 그룹에 들지 않으므로 어휘 목록만으로
오탐을 충분히 설명할 수 없다.

행별 문장·category·activation·trigger view는
`baselines/tensify_false_positives_v1.json`에 저장했다. 아래 명령은 ignored raw prediction에서 같은
진단 JSON을 재생성한다.

```powershell
.\.venv-experiment\Scripts\python `
  -m experiments.benchmark.analyze_tensify_false_positives
```

## 해석 경계

이 dev set은 아직 전 행이 `team_review_needed`이므로 14.06%를 모집단 FPR이나 모델 간 성능값으로
일반화하지 않는다. 현재 근거로 내릴 수 있는 결론은 “후보 정책 때문에 새로 생긴 오탐은 관측되지
않았고, 관측된 오탐은 raw 분류기 원문 판정에서 이미 존재했다”까지다. 최종 FPR과 정책 채택 판정은
검수·봉인된 독립 test에서 다시 계산한다.
