"""배포 경로에 포함되는 선택형 candidate provider namespace.

초성체는 복원 정보가 너무 적어 더 이상 지원하지 않는다. 연음 역복원은 별도의 명시적 opt-in provider로 제공하며 기본
Gateway에는 연결하지 않는다.

무손실 정규화만으로 되돌릴 수 없는 opt-in provider(`spaced_jamo`, `ml_restore`)는 이
namespace에 re-export하지 않는다. 모듈 경로로 직접 import해 `Gateway(providers=[...])`로
주입한다.
"""

from .liaison import LIAISON_CANDIDATE_VERSION, LiaisonInverseProvider


__all__ = ["LIAISON_CANDIDATE_VERSION", "LiaisonInverseProvider"]
