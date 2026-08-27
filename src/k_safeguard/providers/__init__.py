"""배포 경로에 포함되는 선택형 candidate provider namespace.

된소리·초성체 다중 후보 provider는 오탐과 낮은 복원율 때문에 공개 API에서 제거했다.
기존 구현 모듈은 과거 실험 재현용으로만 남긴다.

무손실 정규화만으로 되돌릴 수 없는 opt-in provider(`spaced_jamo`, `ml_restore`)는 이
namespace에 re-export하지 않는다. 모듈 경로로 직접 import해 `Gateway(providers=[...])`로
주입한다.
"""

__all__: list[str] = []
