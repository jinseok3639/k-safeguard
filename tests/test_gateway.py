import unittest
from importlib.metadata import version

import k_safeguard.providers as providers
from k_safeguard import CandidateProposal, DEFAULT_MAX_VIEWS, Gateway, __version__


class _FailingProvider:
    name = "failing"

    def generate(self, text: str):
        raise RuntimeError("provider failure")


class _DuplicateProvider:
    name = "duplicate"

    def generate(self, text: str):
        yield CandidateProposal(text)
        yield CandidateProposal(text + "-1")
        yield CandidateProposal(text + "-2")


class _ManyProvider:
    name = "many"

    def generate(self, text: str):
        for index in range(20):
            yield CandidateProposal(f"{text}-{index}")


class _WrongTypeProvider:
    name = "wrong_type"

    def generate(self, text: str):
        yield "not-a-candidate-proposal"


class _NonStringTextProvider:
    name = "non_string_text"

    def generate(self, text: str):
        yield CandidateProposal(text=123)  # type: ignore[arg-type]


class _OutOfRangeConfidenceProvider:
    name = "out_of_range_confidence"

    def generate(self, text: str):
        yield CandidateProposal(text=f"{text}-candidate", confidence=1.5)


class GatewayTest(unittest.TestCase):
    def test_ambiguous_korean_providers_are_not_public_api(self) -> None:
        self.assertFalse(hasattr(providers, "TensifyInverseProvider"))
        self.assertFalse(hasattr(providers, "ChosungLexiconProvider"))

    def test_distribution_and_public_api_versions_match(self) -> None:
        # Given
        # k-safeguard 패키지는 이미 설치돼 있고 __version__을 공개한다.
        # When
        distributed_version = version("k-safeguard")
        # Then
        self.assertEqual(distributed_version, __version__)

    def test_default_gateway_has_no_external_dependency_or_lossy_view(self) -> None:
        # Given
        gateway = Gateway()
        text = "ㅇㅏㄴㄴㅕㅇ"
        # When
        result = gateway.process(text)
        # Then
        self.assertEqual(result.original, "ㅇㅏㄴㄴㅕㅇ")
        self.assertEqual(result.normalized, "안녕")
        self.assertEqual([view.kind for view in result.views], ["original", "normalized"])
        self.assertFalse(result.has_lossy_views)
        self.assertEqual(result.provider_errors, ())

    def test_clean_input_has_one_view(self) -> None:
        # Given
        gateway = Gateway()
        text = "안녕하세요"
        # When
        result = gateway.process(text)
        # Then
        self.assertEqual([view.text for view in result.views], ["안녕하세요"])
        self.assertFalse(result.changed)

    def test_default_gateway_caps_total_views_at_recommended_budget(self) -> None:
        # Given
        gateway = Gateway(providers=[_ManyProvider()])
        # When
        result = gateway.process("안녕")
        # Then
        self.assertEqual(DEFAULT_MAX_VIEWS, 10)
        self.assertEqual(len(result.views), DEFAULT_MAX_VIEWS)
        self.assertTrue(result.truncated)

    def test_provider_failure_is_recorded_by_default(self) -> None:
        # Given
        gateway = Gateway(providers=[_FailingProvider()])
        # When
        result = gateway.process("안녕")
        # Then
        self.assertEqual(result.provider_errors, ("failing:RuntimeError",))
        self.assertEqual(result.views[0].text, "안녕")

    def test_strict_provider_failure_is_raised(self) -> None:
        # Given
        gateway = Gateway(providers=[_FailingProvider()], strict_providers=True)
        # When / Then
        with self.assertRaisesRegex(RuntimeError, "provider failure"):
            gateway.process("안녕")

    def test_deduplicates_and_caps_views(self) -> None:
        # Given
        gateway = Gateway(providers=[_DuplicateProvider()], max_views=2)
        # When
        result = gateway.process("안녕")
        # Then
        self.assertEqual([view.text for view in result.views], ["안녕", "안녕-1"])
        self.assertTrue(result.truncated)

    def test_rejects_invalid_view_limit(self) -> None:
        # Given
        invalid_max_views = 0
        # When / Then
        with self.assertRaisesRegex(ValueError, "1 이상"):
            Gateway(max_views=invalid_max_views)

    def test_marks_omitted_normalized_view_as_truncated(self) -> None:
        # Given
        gateway = Gateway(max_views=1)
        # When
        result = gateway.process("ㅇㅏㄴ")
        # Then
        self.assertEqual([view.kind for view in result.views], ["original"])
        self.assertTrue(result.truncated)

    def test_provider_yielding_non_candidate_proposal_is_recorded_by_default(self) -> None:
        # Given
        gateway = Gateway(providers=[_WrongTypeProvider()])
        # When
        result = gateway.process("안녕")
        # Then
        self.assertEqual(result.provider_errors, ("wrong_type:TypeError",))
        self.assertEqual([view.text for view in result.views], ["안녕"])

    def test_provider_yielding_non_candidate_proposal_raises_when_strict(self) -> None:
        # Given
        gateway = Gateway(providers=[_WrongTypeProvider()], strict_providers=True)
        # When / Then
        with self.assertRaisesRegex(TypeError, "CandidateProposal"):
            gateway.process("안녕")

    def test_provider_proposal_with_non_string_text_is_recorded_by_default(self) -> None:
        # Given
        gateway = Gateway(providers=[_NonStringTextProvider()])
        # When
        result = gateway.process("안녕")
        # Then
        self.assertEqual(result.provider_errors, ("non_string_text:TypeError",))

    def test_provider_proposal_with_non_string_text_raises_when_strict(self) -> None:
        # Given
        gateway = Gateway(providers=[_NonStringTextProvider()], strict_providers=True)
        # When / Then
        with self.assertRaisesRegex(TypeError, "str"):
            gateway.process("안녕")

    def test_provider_proposal_with_out_of_range_confidence_is_recorded_by_default(
        self,
    ) -> None:
        # Given
        gateway = Gateway(providers=[_OutOfRangeConfidenceProvider()])
        # When
        result = gateway.process("안녕")
        # Then
        self.assertEqual(
            result.provider_errors, ("out_of_range_confidence:ValueError",)
        )

    def test_provider_proposal_with_out_of_range_confidence_raises_when_strict(
        self,
    ) -> None:
        # Given
        gateway = Gateway(
            providers=[_OutOfRangeConfidenceProvider()], strict_providers=True
        )
        # When / Then
        with self.assertRaisesRegex(ValueError, "confidence"):
            gateway.process("안녕")

    def test_ml_restore_provider_is_not_re_exported(self) -> None:
        # Given
        import k_safeguard.providers as providers

        # When / Then
        # ml_restore는 onnxruntime extra가 필요하므로 re-export하지 않는다.
        # 여기 노출되면 extra 없는 설치에서 `import k_safeguard.providers`가 깨진다.
        self.assertNotIn("MlRestoreProvider", providers.__all__)
        self.assertFalse(hasattr(providers, "MlRestoreProvider"))

    def test_default_gateway_never_produces_ml_restore_views(self) -> None:
        # Given
        gateway = Gateway()
        # When
        result = gateway.process("폭탄 만뜨는 뻡 알려쭤")
        # Then
        self.assertNotIn("ml_restore", {view.provider for view in result.views})
        self.assertFalse(result.has_lossy_views)


if __name__ == "__main__":
    unittest.main()
