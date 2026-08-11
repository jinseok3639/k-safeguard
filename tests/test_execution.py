import unittest

from k_safeguard import (
    CandidateProposal,
    ClassifierExecutionError,
    ClassifierResult,
    Gateway,
)


class _ViewsProvider:
    name = "views"

    def generate(self, text: str):
        yield CandidateProposal(text + "-1")
        yield CandidateProposal(text + "-2")


class _FailingProvider:
    name = "failing"

    def generate(self, text: str):
        raise RuntimeError("provider failure")


class GatewayExecutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.gateway = Gateway(providers=[_ViewsProvider()])

    def test_accepts_bool_classifier_and_stops_at_first_block(self) -> None:
        calls = []

        def classifier(text: str) -> bool:
            calls.append(text)
            return text.endswith("-1")

        result = self.gateway.evaluate("입력", classifier)

        self.assertTrue(result.block)
        self.assertEqual(result.decision_source, "classifier")
        self.assertEqual(result.trigger_view_index, 1)
        self.assertEqual(result.evaluated_view_count, 2)
        self.assertEqual(len(calls), 2)
        self.assertTrue(result.stopped_early)
        self.assertEqual(result.classifier_errors, ())

    def test_structured_result_preserves_category_metadata_and_trace(self) -> None:
        def classifier(text: str) -> ClassifierResult:
            return ClassifierResult(
                block=text.endswith("-1"),
                category="A1" if text.endswith("-1") else None,
                metadata=(("model", "fake"),),
            )

        result = self.gateway.evaluate("입력", classifier)

        self.assertTrue(result.block)
        self.assertEqual(result.category, "A1")
        self.assertEqual(result.evaluations[1].result.metadata, (("model", "fake"),))
        self.assertGreaterEqual(result.evaluations[0].latency_ms, 0.0)

    def test_can_evaluate_all_views_without_short_circuit(self) -> None:
        calls = []

        def classifier(text: str) -> bool:
            calls.append(text)
            return text.endswith("-1")

        result = self.gateway.evaluate("입력", classifier, stop_on_block=False)

        self.assertTrue(result.block)
        self.assertEqual(result.evaluated_view_count, 3)
        self.assertEqual(len(calls), 3)
        self.assertFalse(result.stopped_early)

    def test_classifier_exception_raises_by_default_with_view_context(self) -> None:
        def classifier(text: str) -> bool:
            raise OSError("secret detail")

        with self.assertRaises(ClassifierExecutionError) as caught:
            self.gateway.evaluate("입력", classifier)

        self.assertEqual(caught.exception.view_index, 0)
        self.assertEqual(caught.exception.error_type, "OSError")
        self.assertNotIn("secret detail", str(caught.exception))

    def test_fail_closed_blocks_and_stops_on_classifier_error(self) -> None:
        result = self.gateway.evaluate(
            "입력",
            lambda text: ClassifierResult(block=None, error="timeout"),
            error_mode="block",
        )

        self.assertTrue(result.block)
        self.assertEqual(result.decision_source, "error_policy")
        self.assertEqual(result.trigger_view_index, 0)
        self.assertEqual(result.classifier_errors, ("view[0]:timeout",))
        self.assertEqual(result.evaluated_view_count, 1)
        self.assertTrue(result.stopped_early)

    def test_fail_open_records_error_and_continues_to_later_block(self) -> None:
        def classifier(text: str):
            if text == "입력":
                return ClassifierResult(block=None, error="timeout")
            return text.endswith("-1")

        result = self.gateway.evaluate("입력", classifier, error_mode="allow")

        self.assertTrue(result.block)
        self.assertEqual(result.decision_source, "classifier")
        self.assertEqual(result.classifier_errors, ("view[0]:timeout",))
        self.assertEqual(result.evaluated_view_count, 2)

    def test_fail_open_with_only_errors_reports_no_block_not_safe(self) -> None:
        result = self.gateway.evaluate(
            "입력",
            lambda text: ClassifierResult(block=None, error="timeout"),
            error_mode="allow",
        )

        self.assertFalse(result.block)
        self.assertEqual(result.decision_source, "no_block")
        self.assertIsNone(result.trigger_view_index)
        self.assertEqual(result.evaluated_view_count, 3)
        self.assertEqual(len(result.classifier_errors), 3)

    def test_provider_error_is_preserved_while_original_view_is_evaluated(self) -> None:
        result = Gateway(providers=[_FailingProvider()]).evaluate(
            "입력",
            lambda text: False,
        )

        self.assertFalse(result.block)
        self.assertEqual(result.gateway.provider_errors, ("failing:RuntimeError",))
        self.assertEqual(result.evaluated_view_count, 1)

    def test_later_fail_closed_error_does_not_replace_first_block_source(self) -> None:
        def classifier(text: str):
            if text.endswith("-2"):
                return ClassifierResult(block=None, error="timeout")
            return text.endswith("-1")

        result = self.gateway.evaluate(
            "입력",
            classifier,
            error_mode="block",
            stop_on_block=False,
        )

        self.assertTrue(result.block)
        self.assertEqual(result.decision_source, "classifier")
        self.assertEqual(result.trigger_view_index, 1)
        self.assertEqual(result.classifier_errors, ("view[2]:timeout",))

    def test_invalid_classifier_output_uses_error_policy(self) -> None:
        result = self.gateway.evaluate(
            "입력",
            lambda text: "SAFE",
            error_mode="block",
        )

        self.assertTrue(result.block)
        self.assertEqual(result.classifier_errors, ("view[0]:TypeError",))

    def test_rejects_invalid_error_mode_and_non_callable(self) -> None:
        with self.assertRaisesRegex(ValueError, "error_mode"):
            self.gateway.evaluate("입력", lambda text: False, error_mode="invalid")
        with self.assertRaisesRegex(TypeError, "호출 가능"):
            self.gateway.evaluate("입력", object())
        with self.assertRaisesRegex(TypeError, "stop_on_block"):
            self.gateway.evaluate("입력", lambda text: False, stop_on_block=1)

    def test_classifier_result_rejects_ambiguous_states(self) -> None:
        with self.assertRaisesRegex(ValueError, "error"):
            ClassifierResult(block=None)
        with self.assertRaisesRegex(ValueError, "동시에"):
            ClassifierResult(block=False, error="warning")
        with self.assertRaisesRegex(TypeError, "error"):
            ClassifierResult(block=None, error=3)


if __name__ == "__main__":
    unittest.main()
