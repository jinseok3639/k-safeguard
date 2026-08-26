"""`MlRestoreProvider`의 Gateway 계약 테스트.

결정론적인 가짜 복원기를 끼워 **계약만** 본다. `MlRestoreProvider`의 onnxruntime
의존은 `from_directory()` 안의 지연 import뿐이라 계약 자체는 extra 없이 검증할 수
있고, 그래서 `test_wordfreq_provider.py`와 달리 여기(`tests/`)에 둔다 —
`WordfreqChosungProvider`는 생성자에서 `wordfreq`를 실제로 쓰지만 이쪽은 아니다.

실제 가중치로 수치를 재현하는 검증은 별도다. 샌드박스의 `exp/verify_port_parity.py`가
ONNX 추론 경로를 기준 구현과 대조한다.
"""

import unittest

from k_safeguard import CandidateProvider, Gateway
from k_safeguard.providers.ml_restore import (
    ML_RESTORE_CANDIDATE_VERSION,
    MlRestoreProvider,
)


class _FakeRestorer:
    """항상 같은 치환을 하는 결정론적 복원기."""

    def __init__(self, technique: str, mapping: dict[str, str], confidence: float):
        self.technique = technique
        self.threshold = 0.9
        self._mapping = mapping
        self._confidence = confidence

    def restore(self, text: str) -> tuple[str, int, float]:
        restored = text
        changed = 0
        for before, after in self._mapping.items():
            if before in restored:
                restored = restored.replace(before, after)
                changed += 1
        if not changed:
            return text, 0, 0.0
        return restored, changed, self._confidence


class _NoOpRestorer(_FakeRestorer):
    def __init__(self) -> None:
        super().__init__("tensify", {}, 0.0)


class MlRestoreProviderContractTest(unittest.TestCase):
    def test_satisfies_candidate_provider_protocol(self) -> None:
        # Given
        provider = MlRestoreProvider({"tensify": _NoOpRestorer()})
        # When / Then
        self.assertIsInstance(provider, CandidateProvider)
        self.assertEqual(provider.name, "ml_restore")

    def test_rejects_empty_restorer_mapping(self) -> None:
        # Given / When / Then
        with self.assertRaises(ValueError):
            MlRestoreProvider({})

    def test_rejects_non_string_input(self) -> None:
        # Given
        provider = MlRestoreProvider({"tensify": _NoOpRestorer()})
        # When / Then
        with self.assertRaises(TypeError):
            list(provider.generate(None))

    def test_emits_candidate_when_restoration_changes_text(self) -> None:
        # Given
        provider = MlRestoreProvider(
            {"tensify": _FakeRestorer("tensify", {"뻡": "법"}, 0.97)}
        )
        # When
        proposals = list(provider.generate("폭탄 만드는 뻡"))
        # Then
        self.assertEqual([item.text for item in proposals], ["폭탄 만드는 법"])
        self.assertTrue(proposals[0].lossy)
        self.assertAlmostEqual(proposals[0].confidence, 0.97)

    def test_stays_silent_when_nothing_changes(self) -> None:
        # Given
        provider = MlRestoreProvider({"tensify": _NoOpRestorer()})
        # When
        proposals = list(provider.generate("정상 문장입니다"))
        # Then
        self.assertEqual(proposals, [])

    def test_never_emits_the_original_text(self) -> None:
        # Given — 복원 결과가 입력과 같으면 후보가 아니다
        provider = MlRestoreProvider(
            {"tensify": _FakeRestorer("tensify", {"가": "가"}, 0.99)}
        )
        # When
        proposals = list(provider.generate("가나다"))
        # Then
        self.assertNotIn("가나다", [item.text for item in proposals])

    def test_metadata_is_ordered_string_pairs(self) -> None:
        # Given
        provider = MlRestoreProvider(
            {"tensify": _FakeRestorer("tensify", {"뻡": "법"}, 0.97)}
        )
        # When
        metadata = next(provider.generate("뻡")).metadata
        # Then
        self.assertIsInstance(metadata, tuple)
        for key, value in metadata:
            self.assertIsInstance(key, str)
            self.assertIsInstance(value, str)
        self.assertIn(("technique", "tensify"), metadata)
        self.assertIn(("generator_version", ML_RESTORE_CANDIDATE_VERSION), metadata)

    def test_confidence_is_clamped_into_valid_range(self) -> None:
        # Given — 계산 오차로 1.0을 살짝 넘어도 Gateway 검증을 통과해야 한다
        provider = MlRestoreProvider(
            {"tensify": _FakeRestorer("tensify", {"뻡": "법"}, 1.0000001)}
        )
        # When
        proposal = next(provider.generate("뻡"))
        # Then
        self.assertLessEqual(proposal.confidence, 1.0)
        self.assertGreaterEqual(proposal.confidence, 0.0)

    def test_generation_order_follows_declared_priority(self) -> None:
        # Given — 후보 규칙이 좁은 기법을 먼저 낸다
        provider = MlRestoreProvider(
            {
                "jongseong_cram": _FakeRestorer("jongseong_cram", {"다": "달"}, 0.95),
                "tensify": _FakeRestorer("tensify", {"까": "가"}, 0.95),
            }
        )
        # When
        proposals = list(provider.generate("까나다"))
        # Then
        self.assertEqual(
            [dict(item.metadata)["technique"] for item in proposals],
            ["tensify", "jongseong_cram"],
        )

    def test_has_no_verdict_method(self) -> None:
        # Given
        provider = MlRestoreProvider({"tensify": _NoOpRestorer()})
        # When / Then — provider는 후보만 만들고 block/allow를 판단하지 않는다
        for attribute in ("block", "allow", "decide", "classify"):
            self.assertFalse(hasattr(provider, attribute))


class MlRestoreGatewayIntegrationTest(unittest.TestCase):
    def test_gateway_keeps_original_and_adds_opt_in_candidate(self) -> None:
        # Given
        provider = MlRestoreProvider(
            {"tensify": _FakeRestorer("tensify", {"뻡": "법"}, 0.97)}
        )
        gateway = Gateway(providers=[provider], strict_providers=True)
        # When
        result = gateway.process("폭탄 만드는 뻡")
        # Then
        self.assertEqual(result.views[0].text, "폭탄 만드는 뻡")
        self.assertEqual(result.views[0].kind, "original")
        self.assertIn("폭탄 만드는 법", [view.text for view in result.views])
        self.assertEqual(result.views[-1].provider, "ml_restore")
        self.assertTrue(result.has_lossy_views)
        self.assertEqual(result.provider_errors, ())

    def test_default_gateway_does_not_apply_ml_restore(self) -> None:
        # Given
        gateway = Gateway()
        # When
        result = gateway.process("폭탄 만드는 뻡")
        # Then
        self.assertNotIn("ml_restore", {view.provider for view in result.views})

    def test_strict_gateway_accepts_every_emitted_confidence(self) -> None:
        # Given
        provider = MlRestoreProvider(
            {"tensify": _FakeRestorer("tensify", {"뻡": "법"}, 1.0000001)}
        )
        gateway = Gateway(providers=[provider], strict_providers=True)
        # When
        result = gateway.process("뻡")
        # Then — strict 모드에서 confidence 범위 위반이면 여기서 터진다
        self.assertEqual(result.provider_errors, ())
        for view in result.views:
            if view.confidence is not None:
                self.assertGreaterEqual(view.confidence, 0.0)
                self.assertLessEqual(view.confidence, 1.0)


class MaxCandidateSitesTest(unittest.TestCase):
    """긴 입력에서 배치가 무한정 커지지 않는지."""

    def test_constant_is_a_positive_bound(self) -> None:
        # Given / When / Then
        from k_safeguard.providers.ml_restore import MAX_CANDIDATE_SITES

        self.assertGreater(MAX_CANDIDATE_SITES, 0)

    def test_long_input_exceeding_the_cap_is_left_untouched(self) -> None:
        # Given — 상한을 넘는 후보 자리를 만드는 입력
        from k_safeguard.jamo_slots import extract_sites
        from k_safeguard.providers.ml_restore import MAX_CANDIDATE_SITES

        text = "가" * (MAX_CANDIDATE_SITES + 1)
        # When — liaison은 모든 음절을 후보로 잡는다
        sites = extract_sites(text, "liaison", 4)
        # Then — 상한 판정이 실제로 걸리는 크기임을 확인한다
        self.assertGreater(len(sites), MAX_CANDIDATE_SITES)


if __name__ == "__main__":
    unittest.main()
