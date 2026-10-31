"""`MlRestoreProvider`의 Gateway 계약 테스트.

결정론적인 가짜 태거를 끼워 **계약만** 본다. 런타임 의존은 로딩 경로의 지연 import뿐이라
계약 자체는 extra 없이 검증할 수 있다. 실제 가중치로 수치를 재현하는 검증은 실험 저장소의
`restoration/exp/run_p05_2_serving_parity.py`가 맡는다.
"""

import importlib.util
import unittest

from k_safeguard import CandidateProvider, Gateway
from k_safeguard.edit_tags import DELETE, SUBSTITUTE, CharEdit
from k_safeguard.providers.ml_restore import (
    ML_RESTORE_CANDIDATE_VERSION,
    MlRestoreProvider,
    _OnnxEditTagger,
)


class _FakeTagger:
    """정해진 글자를 정해진 확신도로 치환하는 결정론적 태거."""

    def __init__(self, mapping: dict[str, str] | None = None, confidence: float = 0.97):
        self._mapping = mapping or {}
        self._confidence = confidence
        self.calls: list[list[str]] = []

    def predict(self, texts):
        self.calls.append(list(texts))
        return [
            [
                CharEdit(SUBSTITUTE, self._mapping[char], self._confidence)
                if char in self._mapping
                else CharEdit()
                for char in text
            ]
            for text in texts
        ]


def _provider(mapping=None, confidence=0.97, threshold=0.9) -> MlRestoreProvider:
    return MlRestoreProvider(_FakeTagger(mapping, confidence), threshold=threshold)


class MlRestoreProviderContractTest(unittest.TestCase):
    def test_satisfies_candidate_provider_protocol(self) -> None:
        # Given
        provider = _provider()
        # When / Then
        self.assertIsInstance(provider, CandidateProvider)
        self.assertEqual(provider.name, "ml_restore")

    def test_rejects_out_of_range_threshold(self) -> None:
        # Given / When / Then
        with self.assertRaisesRegex(ValueError, "0~1"):
            MlRestoreProvider(_FakeTagger(), threshold=1.5)

    def test_rejects_non_numeric_threshold(self) -> None:
        # Given / When / Then
        with self.assertRaisesRegex(ValueError, "숫자가 아닙니다"):
            MlRestoreProvider(_FakeTagger(), threshold="높게")

    def test_rejects_non_string_input(self) -> None:
        # Given
        provider = _provider()
        # When / Then
        with self.assertRaises(TypeError):
            list(provider.generate(None))

    def test_emits_one_candidate_when_restoration_changes_text(self) -> None:
        # Given
        provider = _provider({"뻡": "법"})
        # When
        proposals = list(provider.generate("폭탄 만드는 뻡"))
        # Then
        self.assertEqual([item.text for item in proposals], ["폭탄 만드는 법"])
        self.assertTrue(proposals[0].lossy)
        self.assertAlmostEqual(proposals[0].confidence, 0.97)

    def test_stays_silent_when_nothing_changes(self) -> None:
        # Given
        provider = _provider()
        # When / Then
        self.assertEqual(list(provider.generate("정상 문장입니다")), [])

    def test_stays_silent_below_threshold(self) -> None:
        # Given — 예측은 있지만 확신이 모자라 기권한다
        provider = _provider({"뻡": "법"}, confidence=0.5, threshold=0.9)
        # When / Then
        self.assertEqual(list(provider.generate("뻡")), [])

    def test_empty_input_never_reaches_the_model(self) -> None:
        # Given
        tagger = _FakeTagger()
        provider = MlRestoreProvider(tagger, threshold=0.9)
        # When
        proposals = list(provider.generate(""))
        # Then
        self.assertEqual(proposals, [])
        self.assertEqual(tagger.calls, [])

    def test_restore_batch_keeps_input_order_around_empty_strings(self) -> None:
        # Given
        provider = _provider({"뻡": "법"})
        # When
        restored = [item[0] for item in provider.restore_batch(["뻡", "", "다"])]
        # Then
        self.assertEqual(restored, ["법", "", "다"])

    def test_metadata_is_ordered_string_pairs(self) -> None:
        # Given
        provider = _provider({"뻡": "법"})
        # When
        metadata = next(provider.generate("뻡")).metadata
        # Then
        self.assertIsInstance(metadata, tuple)
        for key, value in metadata:
            self.assertIsInstance(key, str)
            self.assertIsInstance(value, str)
        self.assertIn(("edits_applied", "1"), metadata)
        self.assertIn(("generator_version", ML_RESTORE_CANDIDATE_VERSION), metadata)

    def test_confidence_is_clamped_into_valid_range(self) -> None:
        # Given — 계산 오차로 1.0을 살짝 넘어도 Gateway 검증을 통과해야 한다
        provider = _provider({"뻡": "법"}, confidence=1.0000001)
        # When
        proposal = next(provider.generate("뻡"))
        # Then
        self.assertLessEqual(proposal.confidence, 1.0)

    def test_has_no_verdict_method(self) -> None:
        # Given
        provider = _provider()
        # When / Then — provider는 후보만 만들고 block/allow를 판단하지 않는다
        for attribute in ("block", "allow", "decide", "classify"):
            self.assertFalse(hasattr(provider, attribute))


class MlRestoreGatewayIntegrationTest(unittest.TestCase):
    def test_gateway_keeps_original_and_adds_opt_in_candidate(self) -> None:
        # Given
        gateway = Gateway(providers=[_provider({"뻡": "법"})], strict_providers=True)
        # When
        result = gateway.process("폭탄 만드는 뻡")
        # Then
        self.assertEqual(result.views[0].text, "폭탄 만드는 뻡")
        self.assertEqual(result.views[0].kind, "original")
        self.assertIn("폭탄 만드는 법", [view.text for view in result.views])
        self.assertEqual(result.views[-1].provider, "ml_restore")
        self.assertTrue(result.has_lossy_views)
        self.assertEqual(result.provider_errors, ())

    def test_provider_receives_the_losslessly_normalized_text(self) -> None:
        # Given
        tagger = _FakeTagger()
        gateway = Gateway(providers=[MlRestoreProvider(tagger, threshold=0.9)])
        # When
        gateway.process("ㅇㅏㄴㄴㅕㅇ")
        # Then
        self.assertEqual(tagger.calls, [["안녕"]])

    def test_default_gateway_does_not_apply_ml_restore(self) -> None:
        # Given / When
        result = Gateway().process("폭탄 만드는 뻡")
        # Then
        self.assertNotIn("ml_restore", {view.provider for view in result.views})


@unittest.skipUnless(importlib.util.find_spec("numpy"), "ml-restore extra가 필요하다")
class OnnxEditTaggerDecodingTest(unittest.TestCase):
    """가짜 세션과 토크나이저로 입력 인코딩과 출력 해석을 본다."""

    class _Encoding:
        def __init__(self, ids, offsets):
            self.ids = ids
            self.attention_mask = [1 if token else 0 for token in ids]
            self.offsets = offsets

    class _Tokenizer:
        def __init__(self, encodings):
            self._encodings = encodings

        def encode_batch(self, texts):
            return self._encodings

    class _Session:
        def __init__(self, outputs):
            self.outputs = outputs
            self.inputs = None

        def run(self, names, inputs):
            self.inputs = inputs
            return self.outputs

    @staticmethod
    def _logits(shape, hot: dict):
        import numpy as np

        values = np.zeros(shape, dtype=np.float32)
        for index, column in hot.items():
            values[(0, index, column)] = 20.0
        return values

    def _tagger(self, text: str, *, ops, spaces, cho, jung, jong, max_chars=384):
        length = min(len(text), max_chars)
        outputs = [
            self._logits((1, length, 3), ops),
            self._logits((1, length, 2), spaces),
            self._logits((1, length, 19), cho),
            self._logits((1, length, 21), jung),
            self._logits((1, length, 28), jong),
        ]
        session = self._Session(outputs)
        encoding = self._Encoding([2, 7, 3], [(0, 0), (0, 2), (0, 0)])
        tagger = _OnnxEditTagger(session, self._Tokenizer([encoding]), {"가": 5}, max_chars)
        return tagger, session

    def test_builds_model_inputs_with_expected_names_and_values(self) -> None:
        # Given
        tagger, session = self._tagger(
            "가a", ops={0: 0, 1: 0}, spaces={0: 0, 1: 0}, cho={}, jung={}, jong={}
        )
        # When
        tagger.predict(["가a"])
        # Then
        inputs = session.inputs
        self.assertEqual(inputs["chars"].tolist(), [[5, 1]])    # 어휘 밖 글자는 UNK(1)
        self.assertEqual(inputs["slots"].tolist(), [[[1, 1, 1], [0, 0, 0]]])
        self.assertEqual(inputs["char_to_token"].tolist(), [[1, 1]])
        self.assertEqual(inputs["covered"].tolist(), [[1, 1]])

    def test_decodes_substitution_from_slot_heads(self) -> None:
        # Given — 초성 ㅂ(7), 중성 ㅓ(4), 종성 ㅂ(17) = 법
        tagger, _ = self._tagger(
            "뻡", ops={0: SUBSTITUTE}, spaces={0: 0}, cho={0: 7}, jung={0: 4}, jong={0: 17}
        )
        # When
        edit = tagger.predict(["뻡"])[0][0]
        # Then
        self.assertEqual(edit.op, SUBSTITUTE)
        self.assertEqual(edit.replacement, "법")
        self.assertGreater(edit.confidence, 0.99)

    def test_substitution_to_the_same_syllable_becomes_keep(self) -> None:
        # Given — 초성 ㅂ(7), 중성 ㅓ(4), 종성 ㅂ(17) = 법
        tagger, _ = self._tagger(
            "법", ops={0: SUBSTITUTE}, spaces={0: 0}, cho={0: 7}, jung={0: 4}, jong={0: 17}
        )
        # When / Then
        self.assertEqual(tagger.predict(["법"])[0][0].replacement, "")

    def test_decodes_deletion_and_space(self) -> None:
        # Given
        tagger, _ = self._tagger(
            "!", ops={0: DELETE}, spaces={0: 1}, cho={}, jung={}, jong={}
        )
        # When
        edit = tagger.predict(["!"])[0][0]
        # Then
        self.assertEqual(edit.op, DELETE)
        self.assertGreater(edit.space_confidence, 0.99)

    def test_characters_beyond_max_chars_are_left_alone(self) -> None:
        # Given
        tagger, session = self._tagger(
            "가가가", ops={0: 0, 1: 0}, spaces={0: 0, 1: 0}, cho={}, jung={}, jong={}, max_chars=2
        )
        # When
        edits = tagger.predict(["가가가"])[0]
        # Then
        self.assertEqual(session.inputs["chars"].shape, (1, 2))
        self.assertEqual(len(edits), 3)
        self.assertEqual(edits[2], CharEdit())


if __name__ == "__main__":
    unittest.main()
