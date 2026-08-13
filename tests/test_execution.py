import asyncio
import unittest

from k_safeguard import (
    BatchClassifierOutputError,
    CandidateProposal,
    ClassifierExecutionError,
    ClassifierResult,
    Gateway,
    evaluate_gateway_async,
    evaluate_gateway_batch,
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
        self.assertEqual(result.classifier_call_count, 2)
        self.assertEqual(result.classifier_calls[1].view_indices, (1,))
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

    def test_classifier_result_rejects_non_bool_block_and_non_str_category(self) -> None:
        with self.assertRaisesRegex(TypeError, "bool"):
            ClassifierResult(block="yes")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "category"):
            ClassifierResult(block=True, category=1)  # type: ignore[arg-type]

    def test_fail_raise_mode_surfaces_explicit_classifier_error_without_a_cause(
        self,
    ) -> None:
        with self.assertRaises(ClassifierExecutionError) as caught:
            self.gateway.evaluate(
                "입력",
                lambda text: ClassifierResult(block=None, error="timeout"),
            )

        self.assertEqual(caught.exception.view_index, 0)
        self.assertIsNone(caught.exception.__cause__)

    def test_all_views_blocked_keeps_first_trigger_when_not_stopping_early(self) -> None:
        result = self.gateway.evaluate("입력", lambda text: True, stop_on_block=False)

        self.assertTrue(result.block)
        self.assertEqual(result.decision_source, "classifier")
        self.assertEqual(result.trigger_view_index, 0)
        self.assertEqual(result.evaluated_view_count, 3)
        self.assertFalse(result.stopped_early)


class AsyncGatewayExecutionTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.gateway = Gateway(providers=[_ViewsProvider()])

    async def test_async_classifier_preserves_order_and_stops_at_first_block(self) -> None:
        calls = []

        async def classifier(text: str) -> bool:
            await asyncio.sleep(0)
            calls.append(text)
            return text.endswith("-1")

        result = await self.gateway.evaluate_async("입력", classifier)

        self.assertTrue(result.block)
        self.assertEqual(result.decision_source, "classifier")
        self.assertEqual(result.trigger_view_index, 1)
        self.assertEqual(calls, ["입력", "입력-1"])
        self.assertEqual(result.evaluated_view_count, 2)
        self.assertEqual(result.classifier_call_count, 2)
        self.assertTrue(result.stopped_early)

    async def test_async_classifier_can_evaluate_all_views(self) -> None:
        async def classifier(text: str) -> ClassifierResult:
            return ClassifierResult(
                block=text.endswith("-1"),
                category="A1" if text.endswith("-1") else None,
                metadata=(("transport", "async"),),
            )

        result = await self.gateway.evaluate_async(
            "입력",
            classifier,
            stop_on_block=False,
        )

        self.assertTrue(result.block)
        self.assertEqual(result.category, "A1")
        self.assertEqual(result.evaluated_view_count, 3)
        self.assertFalse(result.stopped_early)
        self.assertEqual(
            result.evaluations[1].result.metadata,
            (("transport", "async"),),
        )

    async def test_async_exception_uses_same_error_policy_and_cause(self) -> None:
        async def classifier(text: str) -> bool:
            raise OSError("secret detail")

        with self.assertRaises(ClassifierExecutionError) as caught:
            await self.gateway.evaluate_async("입력", classifier)

        self.assertEqual(caught.exception.view_index, 0)
        self.assertEqual(caught.exception.error_type, "OSError")
        self.assertIsInstance(caught.exception.__cause__, OSError)
        self.assertNotIn("secret detail", str(caught.exception))

    async def test_async_fail_closed_blocks_on_explicit_error(self) -> None:
        async def classifier(text: str) -> ClassifierResult:
            return ClassifierResult(block=None, error="timeout")

        result = await self.gateway.evaluate_async(
            "입력",
            classifier,
            error_mode="block",
        )

        self.assertTrue(result.block)
        self.assertEqual(result.decision_source, "error_policy")
        self.assertEqual(result.classifier_errors, ("view[0]:timeout",))
        self.assertEqual(result.evaluated_view_count, 1)

    async def test_async_fail_open_continues_to_later_block(self) -> None:
        async def classifier(text: str):
            if text == "입력":
                return ClassifierResult(block=None, error="timeout")
            return text.endswith("-1")

        result = await self.gateway.evaluate_async(
            "입력",
            classifier,
            error_mode="allow",
        )

        self.assertTrue(result.block)
        self.assertEqual(result.decision_source, "classifier")
        self.assertEqual(result.trigger_view_index, 1)
        self.assertEqual(result.classifier_errors, ("view[0]:timeout",))

    async def test_async_api_rejects_sync_classifier_via_error_policy(self) -> None:
        result = await self.gateway.evaluate_async(
            "입력",
            lambda text: False,
            error_mode="block",
        )

        self.assertTrue(result.block)
        self.assertEqual(result.classifier_errors, ("view[0]:TypeError",))

    async def test_async_cancellation_is_not_converted_to_classifier_error(self) -> None:
        async def classifier(text: str) -> bool:
            raise asyncio.CancelledError

        with self.assertRaises(asyncio.CancelledError):
            await self.gateway.evaluate_async("입력", classifier, error_mode="block")

    async def test_low_level_async_function_is_public(self) -> None:
        async def classifier(text: str) -> bool:
            return False

        gateway_result = self.gateway.process("입력")
        result = await evaluate_gateway_async(gateway_result, classifier)

        self.assertFalse(result.block)
        self.assertEqual(result.evaluated_view_count, 3)


class BatchGatewayExecutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.gateway = Gateway(providers=[_ViewsProvider()])

    def test_batch_classifier_receives_all_views_in_one_ordered_call(self) -> None:
        calls = []

        def classifier(texts: tuple[str, ...]):
            calls.append(texts)
            return [text.endswith("-1") for text in texts]

        result = self.gateway.evaluate_batch("입력", classifier)

        self.assertTrue(result.block)
        self.assertEqual(result.trigger_view_index, 1)
        self.assertEqual(calls, [("입력", "입력-1", "입력-2")])
        self.assertEqual(result.evaluated_view_count, 3)
        self.assertEqual(result.classifier_call_count, 1)
        self.assertEqual(result.classifier_calls[0].view_indices, (0, 1, 2))
        self.assertFalse(result.stopped_early)
        self.assertTrue(
            all(
                item.latency_ms == result.classifier_calls[0].latency_ms
                for item in result.evaluations
            )
        )

    def test_bounded_batch_stops_before_next_chunk(self) -> None:
        calls = []

        def classifier(texts: tuple[str, ...]):
            calls.append(texts)
            return [text.endswith("-1") for text in texts]

        result = self.gateway.evaluate_batch("입력", classifier, batch_size=2)

        self.assertTrue(result.block)
        self.assertEqual(calls, [("입력", "입력-1")])
        self.assertEqual(result.evaluated_view_count, 2)
        self.assertEqual(result.classifier_call_count, 1)
        self.assertTrue(result.stopped_early)

    def test_batch_can_run_all_chunks_without_short_circuit(self) -> None:
        calls = []

        def classifier(texts: tuple[str, ...]):
            calls.append(texts)
            return [text.endswith("-1") for text in texts]

        result = self.gateway.evaluate_batch(
            "입력",
            classifier,
            batch_size=2,
            stop_on_block=False,
        )

        self.assertTrue(result.block)
        self.assertEqual(calls, [("입력", "입력-1"), ("입력-2",)])
        self.assertEqual(result.classifier_call_count, 2)
        self.assertEqual(result.classifier_calls[1].view_indices, (2,))
        self.assertFalse(result.stopped_early)

    def test_batch_preserves_structured_result_and_first_category(self) -> None:
        def classifier(texts: tuple[str, ...]):
            return [
                ClassifierResult(
                    block=text.endswith("-1"),
                    category="A1" if text.endswith("-1") else None,
                    metadata=(("mode", "batch"),),
                )
                for text in texts
            ]

        result = self.gateway.evaluate_batch("입력", classifier)

        self.assertEqual(result.category, "A1")
        self.assertEqual(
            result.evaluations[1].result.metadata,
            (("mode", "batch"),),
        )

    def test_batch_output_count_mismatch_raises_with_safe_context(self) -> None:
        with self.assertRaises(ClassifierExecutionError) as caught:
            self.gateway.evaluate_batch("입력", lambda texts: [False])

        self.assertEqual(caught.exception.view_index, 0)
        self.assertEqual(
            caught.exception.error_type,
            "BatchClassifierOutputError",
        )
        self.assertIsInstance(
            caught.exception.__cause__,
            BatchClassifierOutputError,
        )

    def test_fail_closed_records_every_view_submitted_in_failed_batch(self) -> None:
        result = self.gateway.evaluate_batch(
            "입력",
            lambda texts: [False],
            batch_size=2,
            error_mode="block",
        )

        self.assertTrue(result.block)
        self.assertEqual(result.trigger_view_index, 0)
        self.assertEqual(result.evaluated_view_count, 2)
        self.assertEqual(
            result.classifier_errors,
            (
                "view[0]:BatchClassifierOutputError",
                "view[1]:BatchClassifierOutputError",
            ),
        )
        self.assertTrue(result.stopped_early)

    def test_invalid_item_uses_error_policy_without_discarding_valid_items(self) -> None:
        result = self.gateway.evaluate_batch(
            "입력",
            lambda texts: [False, "SAFE", True],
            error_mode="allow",
        )

        self.assertTrue(result.block)
        self.assertEqual(result.trigger_view_index, 2)
        self.assertEqual(result.classifier_errors, ("view[1]:TypeError",))
        self.assertEqual(result.evaluated_view_count, 3)

    def test_batch_exception_fail_open_covers_every_submitted_view(self) -> None:
        calls = []

        def classifier(texts: tuple[str, ...]):
            calls.append(texts)
            raise TimeoutError("secret detail")

        result = self.gateway.evaluate_batch(
            "입력",
            classifier,
            batch_size=2,
            error_mode="allow",
        )

        self.assertFalse(result.block)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result.evaluated_view_count, 3)
        self.assertEqual(len(result.classifier_errors), 3)
        self.assertTrue(
            all(error.endswith(":TimeoutError") for error in result.classifier_errors)
        )

    def test_batch_output_as_raw_string_is_rejected_like_invalid_output(self) -> None:
        with self.assertRaises(ClassifierExecutionError) as caught:
            self.gateway.evaluate_batch("입력", lambda texts: "SAFE")

        self.assertEqual(caught.exception.view_index, 0)
        self.assertEqual(caught.exception.error_type, "TypeError")
        self.assertIsInstance(caught.exception.__cause__, TypeError)

    def test_non_iterable_batch_output_is_rejected(self) -> None:
        with self.assertRaises(ClassifierExecutionError) as caught:
            self.gateway.evaluate_batch("입력", lambda texts: None)

        self.assertEqual(caught.exception.view_index, 0)
        self.assertEqual(caught.exception.error_type, "TypeError")
        self.assertIsInstance(caught.exception.__cause__, TypeError)

    def test_rejects_invalid_batch_size(self) -> None:
        classifier = lambda texts: [False for _ in texts]
        with self.assertRaisesRegex(ValueError, "1 이상"):
            self.gateway.evaluate_batch("입력", classifier, batch_size=0)
        with self.assertRaisesRegex(TypeError, "int"):
            self.gateway.evaluate_batch("입력", classifier, batch_size=True)
        with self.assertRaisesRegex(TypeError, "int"):
            self.gateway.evaluate_batch("입력", classifier, batch_size=1.5)

    def test_low_level_batch_function_is_public(self) -> None:
        gateway_result = self.gateway.process("입력")
        result = evaluate_gateway_batch(
            gateway_result,
            lambda texts: [False for _ in texts],
        )

        self.assertFalse(result.block)
        self.assertEqual(result.classifier_call_count, 1)


class AsyncBatchGatewayExecutionTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.gateway = Gateway(providers=[_ViewsProvider()])

    async def test_async_batch_classifier_uses_bounded_chunks(self) -> None:
        calls = []

        async def classifier(texts: tuple[str, ...]):
            await asyncio.sleep(0)
            calls.append(texts)
            return [text.endswith("-1") for text in texts]

        result = await self.gateway.evaluate_batch_async(
            "입력",
            classifier,
            batch_size=2,
        )

        self.assertTrue(result.block)
        self.assertEqual(calls, [("입력", "입력-1")])
        self.assertEqual(result.evaluated_view_count, 2)
        self.assertEqual(result.classifier_call_count, 1)
        self.assertTrue(result.stopped_early)

    async def test_async_batch_can_evaluate_all_chunks(self) -> None:
        async def classifier(texts: tuple[str, ...]):
            return [False for _ in texts]

        result = await self.gateway.evaluate_batch_async(
            "입력",
            classifier,
            batch_size=2,
        )

        self.assertFalse(result.block)
        self.assertEqual(result.evaluated_view_count, 3)
        self.assertEqual(result.classifier_call_count, 2)

    async def test_async_batch_exception_fail_open_covers_every_submitted_view(
        self,
    ) -> None:
        calls = []

        async def classifier(texts: tuple[str, ...]):
            calls.append(texts)
            raise TimeoutError("secret detail")

        result = await self.gateway.evaluate_batch_async(
            "입력",
            classifier,
            batch_size=2,
            error_mode="allow",
        )

        self.assertFalse(result.block)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result.evaluated_view_count, 3)
        self.assertEqual(len(result.classifier_errors), 3)
        self.assertTrue(
            all(error.endswith(":TimeoutError") for error in result.classifier_errors)
        )

    async def test_async_batch_cancellation_is_propagated(self) -> None:
        async def classifier(texts: tuple[str, ...]):
            raise asyncio.CancelledError

        with self.assertRaises(asyncio.CancelledError):
            await self.gateway.evaluate_batch_async(
                "입력",
                classifier,
                error_mode="block",
            )


if __name__ == "__main__":
    unittest.main()
