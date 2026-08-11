# 된소리 activation 채택 결정

## 최종 결정

- 공개 생성자 기본값: `min_tense_ratio=0.0` 유지
- `ratio_0.10`: **DO_NOT_PROMOTE**, 권장 preset으로 승격하지 않음
- 근거: locked-test ΔFPR-obfuscated +14.29%p, 95% CI 상한 +28.57%p

개발 공격 paired 평가에서 `ratio_0.10`은 NRR 100%를 유지했고, benign dev에서는 `all` 대비
activation이 100%에서 40.62%, 평균 추가 view가 2.09에서 1.25로 줄었다. 이때 raw/all/ratio의
FPR은 모두 9/64였고 정책 때문에 새로 block된 문장은 없었다. 당시 사람 검수 전 개발 자료였고
후속 검수를 거쳤어도 tuning-aware dev이므로 패키지 기본 동작을 바꾸는 근거로는 부족했다. 독립
locked-test에서는 NRR 100%와 clean 비용 절감을 재현했지만 된소리화 benign 4/28이 새로 차단되어
사전등록 오탐 기준을 통과하지 못했다.

## locked-test 판정표

| 조건 | 통과 기준 | 실패 시 |
|---|---|---|
| 데이터 유효성 | 전 행 사람 검수·seal, clean block 공격 ≥20, 오류율 <1%, benign hard-negative 포함 | `INVALID_OR_INCONCLUSIVE` |
| NRR | 점추정 ≥50%, CI 하한 >25%, `all`보다 낮지 않음 | `DO_NOT_PROMOTE` |
| 회복 효과 | recovery gain CI 하한 >0 | `DO_NOT_PROMOTE` |
| 정상 오탐 | clean/obf ΔFPR 각 ≤+2%p, CI 상한 각 ≤+5%p | `DO_NOT_PROMOTE` |
| 무손실성 | clean benign mutation ≤1%, Unicode/provider 오류 0건 | `DO_NOT_PROMOTE` |
| 효율 | clean activation이 `all`보다 낮고 view 비용이 높지 않음 | `DO_NOT_PROMOTE` |

이번 결과는 유효성 gate를 통과했지만 정상 오탐 gate에서 실패했으므로 named preset도 추가하지
않는다. `ratio_0.10`은 연구용 명시 옵션으로만 남는다. 이는 pip 라이브러리가 다른 가드레일 모델과
한국어 도메인에서도 사용되고 기존 사용자의 동작을 예고 없이 바꾸면 안 되기 때문이다.

최종 판정은 `run_tensify_locked_evaluation.py`가 결과와 함께 기계적으로 기록했으며 상태는
**DO_NOT_PROMOTE**다. 상세 결과는 [locked-test v2 결과](./TENSIFY_LOCKED_RESULT.md)를 따른다.
