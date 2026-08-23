import unittest

from k_safeguard import Gateway
from k_safeguard.providers import LIAISON_CANDIDATE_VERSION, LiaisonInverseProvider


class LiaisonInverseProviderTest(unittest.TestCase):
    def test_reverses_simple_liaison(self) -> None:
        provider = LiaisonInverseProvider(max_candidates=1)

        proposals = list(provider.generate("머글게"))

        self.assertEqual([proposal.text for proposal in proposals], ["먹을게"])
        self.assertTrue(proposals[0].lossy)
        self.assertIsNone(proposals[0].confidence)
        self.assertIn(
            ("generator_version", LIAISON_CANDIDATE_VERSION),
            proposals[0].metadata,
        )

    def test_reverses_aspirated_surface_onset(self) -> None:
        provider = LiaisonInverseProvider(max_candidates=1)

        proposal = next(provider.generate("꼬치"))

        self.assertEqual(proposal.text, "꽃이")

    def test_orders_single_pair_candidates_before_combinations(self) -> None:
        provider = LiaisonInverseProvider(max_candidates=3)

        proposals = list(provider.generate("가나다라"))

        self.assertEqual(
            [proposal.text for proposal in proposals],
            ["간아다라", "가나달아", "간아달아"],
        )
        self.assertEqual(
            proposals[0].metadata,
            (
                ("replacement_count", "1"),
                ("candidate_pairs", "2"),
                ("min_pairs", "1"),
                ("source_positions", "0"),
                ("generator_version", LIAISON_CANDIDATE_VERSION),
            ),
        )

    def test_preserves_vowels_and_right_final(self) -> None:
        provider = LiaisonInverseProvider(max_candidates=1)

        proposal = next(provider.generate("머근"))

        self.assertEqual(proposal.text, "먹은")

    def test_excludes_unsupported_onsets_and_boundaries(self) -> None:
        provider = LiaisonInverseProvider()

        self.assertEqual(list(provider.generate("강아")), [])
        self.assertEqual(list(provider.generate("머 글게")), [])
        self.assertEqual(list(provider.generate("가하")), [])

    def test_minimum_pair_activation_is_opt_in(self) -> None:
        provider = LiaisonInverseProvider(min_pairs=2)

        self.assertEqual(list(provider.generate("머글게")), [])
        self.assertTrue(list(provider.generate("가나다라")))

    def test_caps_candidates_deterministically(self) -> None:
        provider = LiaisonInverseProvider(max_candidates=2)

        first = [proposal.text for proposal in provider.generate("가나다라")]
        second = [proposal.text for proposal in provider.generate("가나다라")]

        self.assertEqual(first, second)
        self.assertEqual(len(first), 2)

    def test_rejects_invalid_configuration_and_non_string_input(self) -> None:
        with self.assertRaisesRegex(ValueError, "max_candidates"):
            LiaisonInverseProvider(max_candidates=0)
        with self.assertRaisesRegex(ValueError, "min_pairs"):
            LiaisonInverseProvider(min_pairs=0)

        provider = LiaisonInverseProvider()
        with self.assertRaisesRegex(TypeError, "str"):
            list(provider.generate(None))  # type: ignore[arg-type]

    def test_gateway_keeps_original_and_adds_lossy_candidate(self) -> None:
        result = Gateway(providers=[LiaisonInverseProvider(max_candidates=1)]).process(
            "머글게"
        )

        self.assertEqual([view.text for view in result.views], ["머글게", "먹을게"])
        self.assertEqual(result.views[1].provider, "liaison_inverse")
        self.assertTrue(result.has_lossy_views)

    def test_default_gateway_does_not_reverse_liaison(self) -> None:
        result = Gateway().process("머글게")

        self.assertEqual([view.text for view in result.views], ["머글게"])
        self.assertFalse(result.has_lossy_views)


if __name__ == "__main__":
    unittest.main()
