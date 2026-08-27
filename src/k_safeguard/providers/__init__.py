"""배포 경로에 포함되는 선택형 candidate provider namespace.

된소리·초성체 다중 후보 provider는 오탐과 낮은 복원율 때문에 공개 API에서 제거했다.
기존 구현 모듈은 과거 실험 재현용으로만 남긴다. 연음 역복원은 별도의 명시적
opt-in provider로 제공하며 기본 Gateway에는 연결하지 않는다.
"""

from .liaison import LIAISON_CANDIDATE_VERSION, LiaisonInverseProvider


__all__ = ["LIAISON_CANDIDATE_VERSION", "LiaisonInverseProvider"]
