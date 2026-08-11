import unittest
from importlib.metadata import version

from k_safeguard import CandidateProposal, DEFAULT_MAX_VIEWS, Gateway, __version__
from k_safeguard.chosung import ChosungLexicon
from k_safeguard.providers import ChosungLexiconProvider


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


class GatewayTest(unittest.TestCase):
    def test_distribution_and_public_api_versions_match(self) -> None:
        self.assertEqual(version("k-safeguard"), __version__)

    def test_default_gateway_has_no_external_dependency_or_lossy_view(self) -> None:
        result = Gateway().process("ㅇㅏㄴㄴㅕㅇ")
        self.assertEqual(result.original, "ㅇㅏㄴㄴㅕㅇ")
        self.assertEqual(result.normalized, "안녕")
        self.assertEqual([view.kind for view in result.views], ["original", "normalized"])
        self.assertFalse(result.has_lossy_views)
        self.assertEqual(result.provider_errors, ())

    def test_clean_input_has_one_view(self) -> None:
        result = Gateway().process("안녕하세요")
        self.assertEqual([view.text for view in result.views], ["안녕하세요"])
        self.assertFalse(result.changed)

    def test_default_gateway_caps_total_views_at_recommended_budget(self) -> None:
        result = Gateway(providers=[_ManyProvider()]).process("안녕")

        self.assertEqual(DEFAULT_MAX_VIEWS, 10)
        self.assertEqual(len(result.views), DEFAULT_MAX_VIEWS)
        self.assertTrue(result.truncated)

    def test_chosung_provider_is_explicit_opt_in(self) -> None:
        lexicon = ChosungLexicon.from_sources(
            [("user", ["시스템"]), ("general", ["산사태"])]
        )
        provider = ChosungLexiconProvider(lexicon)
        result = Gateway(providers=[provider]).process("ㅅㅅㅌ 점검")
        self.assertEqual(result.views[0].text, "ㅅㅅㅌ 점검")
        self.assertIn("시스템 점검", [view.text for view in result.views])
        self.assertTrue(result.has_lossy_views)
        self.assertEqual(result.views[1].provider, "chosung_lexicon")
        self.assertIn(("lexicon_sources", "user"), result.views[1].metadata)

    def test_provider_failure_is_recorded_by_default(self) -> None:
        result = Gateway(providers=[_FailingProvider()]).process("안녕")
        self.assertEqual(result.provider_errors, ("failing:RuntimeError",))
        self.assertEqual(result.views[0].text, "안녕")

    def test_chosung_provider_can_opt_in_to_segmented_candidates(self) -> None:
        lexicon = ChosungLexicon.from_sources(
            [("domain", ["시스템", "프롬프트"])]
        )
        provider = ChosungLexiconProvider(lexicon, allow_segmentation=True)

        result = Gateway(providers=[provider]).process("ㅅㅅㅌㅍㄹㅍㅌ")
        self.assertEqual(result.views[1].text, "시스템프롬프트")
        self.assertIn(("max_segment_count", "2"), result.views[1].metadata)

    def test_chosung_provider_can_restore_one_trusted_partial_range(self) -> None:
        lexicon = ChosungLexicon.from_sources(
            [("domain", ["시스템"]), ("general", ["산사태"])]
        )
        provider = ChosungLexiconProvider(
            lexicon,
            allow_partial_restoration=True,
            partial_sources=("domain",),
        )

        result = Gateway(providers=[provider]).process("ㄱㄱㅅㅅㅌㄴ")

        self.assertEqual(result.views[1].text, "ㄱㄱ시스템ㄴ")
        self.assertIn(("partial_replacement_count", "1"), result.views[1].metadata)
        self.assertIn(("partial_ranges", "2:5"), result.views[1].metadata)

    def test_chosung_provider_rejects_one_string_as_partial_sources(self) -> None:
        lexicon = ChosungLexicon.from_sources([("domain", ["시스템"])])
        with self.assertRaisesRegex(TypeError, "iterable"):
            ChosungLexiconProvider(
                lexicon,
                allow_partial_restoration=True,
                partial_sources="domain",
            )

    def test_strict_provider_failure_is_raised(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "provider failure"):
            Gateway(providers=[_FailingProvider()], strict_providers=True).process("안녕")

    def test_deduplicates_and_caps_views(self) -> None:
        result = Gateway(providers=[_DuplicateProvider()], max_views=2).process("안녕")
        self.assertEqual([view.text for view in result.views], ["안녕", "안녕-1"])
        self.assertTrue(result.truncated)

    def test_rejects_invalid_view_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "1 이상"):
            Gateway(max_views=0)

    def test_marks_omitted_normalized_view_as_truncated(self) -> None:
        result = Gateway(max_views=1).process("ㅇㅏㄴ")
        self.assertEqual([view.kind for view in result.views], ["original"])
        self.assertTrue(result.truncated)


if __name__ == "__main__":
    unittest.main()
