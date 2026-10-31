"""`Gateway.normalize()`가 문장 하나를 고르는 규칙 테스트."""

import unittest

from k_safeguard import CandidateProposal, Gateway


class _Provider:
    name = "fake"

    def __init__(self, *proposals: CandidateProposal) -> None:
        self._proposals = proposals

    def generate(self, text: str):
        return iter(self._proposals)


class _BrokenProvider:
    name = "broken"

    def generate(self, text: str):
        raise RuntimeError("모델 장애")


class GatewayNormalizeTest(unittest.TestCase):
    def test_without_providers_returns_lossless_result(self) -> None:
        # Given / When / Then
        self.assertEqual(Gateway().normalize("ㅇㅏㄴㄴㅕㅇ"), "안녕")

    def test_clean_text_is_unchanged(self) -> None:
        # Given / When / Then
        self.assertEqual(Gateway().normalize("안녕하세요"), "안녕하세요")

    def test_picks_the_most_confident_candidate(self) -> None:
        # Given
        provider = _Provider(
            CandidateProposal("낮음", confidence=0.6),
            CandidateProposal("높음", confidence=0.9),
        )
        # When / Then
        self.assertEqual(Gateway(providers=[provider]).normalize("입력"), "높음")

    def test_ignores_candidates_without_confidence(self) -> None:
        # Given — 나열된 후보는 어느 것이 맞는지 알 수 없다
        provider = _Provider(CandidateProposal("추측", confidence=None))
        # When / Then
        self.assertEqual(Gateway(providers=[provider]).normalize("입력"), "입력")

    def test_provider_failure_falls_back_to_lossless_result(self) -> None:
        # Given
        gateway = Gateway(providers=[_BrokenProvider()])
        # When / Then
        self.assertEqual(gateway.normalize("ㅇㅏㄴ"), "안")


if __name__ == "__main__":
    unittest.main()
