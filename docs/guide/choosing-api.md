# API 선택

문장 하나가 필요하면 `normalize()`, 차단 판정이 필요하면 `evaluate` 계열, 직접 고르려면 `process()`를 씁니다.

| 하려는 일 | API | provider |
|---|---|---|
| 자모 분해, ZWSP, 반각 자모만 안전하게 정리 | `Gateway().normalize` | 없음 |
| 변경 위치 기록 | `normalize_korean` | 없음 |
| 된소리, 받침 변형까지 한 문장으로 복원 | `Gateway.normalize` | `MlRestoreProvider` |
| 후보를 사람이나 후처리가 검토 | `Gateway.process` | 필요한 것 |
| 가드레일 동기 호출 | `Gateway.evaluate` | 선택 |
| 원격 async API | `Gateway.evaluate_async` | 선택 |
| 로컬 모델 batch | `Gateway.evaluate_batch` | 선택 |
| 원격 async batch | `Gateway.evaluate_batch_async` | 선택 |
| 같은 view로 모델 비교 | `evaluate_gateway` 계열 | 선택 |
| 띄어 쓴 자모 탐지 | `process`, `evaluate` | `SpacedJamoProvider` |
| 연음 표기 탐지 | `evaluate` | `LiaisonInverseProvider` |

## provider 비교

| provider | 대상 | 후보 수 | `confidence` | 추가 설치 |
|---|---|---|---|---|
| `SpacedJamoProvider` | 띄어 쓴 자모 | 0 또는 1 | `None` | 없음 |
| `LiaisonInverseProvider` | 단순 연음 | `max_candidates`까지 | `None` | 없음 |
| `MlRestoreProvider` | 복합 난독화 | 0 또는 1 | 평균 확신도 | `ml-restore` extra, 가중치 |
