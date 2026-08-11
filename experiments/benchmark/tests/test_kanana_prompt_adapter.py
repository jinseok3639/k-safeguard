import unittest

from experiments.benchmark.adapters.kanana_prompt import (
    AdapterResult,
    KananaPromptAdapter,
    hash_token_ids,
    normalize_device_map,
    parse_kanana_prompt_output,
    to_classifier_result,
)


class ParseKananaPromptOutputTest(unittest.TestCase):
    def test_safe(self) -> None:
        self.assertEqual(parse_kanana_prompt_output("<SAFE>"), (False, None, None))

    def test_a1(self) -> None:
        self.assertEqual(parse_kanana_prompt_output("<UNSAFE-A1>"), (True, "A1", None))

    def test_a2_with_surrounding_whitespace(self) -> None:
        self.assertEqual(parse_kanana_prompt_output("  <UNSAFE-A2>\n"), (True, "A2", None))

    def test_unknown_is_invalid_not_safe(self) -> None:
        self.assertEqual(parse_kanana_prompt_output("UNKNOWN"), (None, None, "invalid_output"))

    def test_token_hash_is_deterministic_and_order_sensitive(self) -> None:
        self.assertEqual(hash_token_ids([1, 2, 3]), hash_token_ids([1, 2, 3]))
        self.assertNotEqual(hash_token_ids([1, 2, 3]), hash_token_ids([3, 2, 1]))

    def test_device_map_replaces_empty_root_key(self) -> None:
        self.assertEqual(normalize_device_map({"": 0}), {"<root>": "0"})

    def test_converts_adapter_result_to_gateway_classifier_result(self) -> None:
        result = to_classifier_result(
            AdapterResult(
                block=True,
                category="A1",
                raw_output="<UNSAFE-A1>",
                error_type=None,
                latency_ms=12.5,
                input_token_count=7,
                tokenized_input_sha256="abc",
                generated_token_id=42,
            ),
            model_id="model",
            revision="revision",
        )

        self.assertTrue(result.block)
        self.assertEqual(result.category, "A1")
        self.assertEqual(result.error, None)
        self.assertIn(("model_id", "model"), result.metadata)
        self.assertIn(("model_latency_ms", "12.500000"), result.metadata)
        self.assertIn(("generated_token_id", "42"), result.metadata)

    def test_invalid_adapter_output_remains_an_error(self) -> None:
        result = to_classifier_result(
            AdapterResult(
                block=None,
                category=None,
                raw_output="UNKNOWN",
                error_type="invalid_output",
                latency_ms=1.0,
                input_token_count=1,
                tokenized_input_sha256="abc",
                generated_token_id=None,
            ),
            model_id="model",
            revision="revision",
        )

        self.assertIsNone(result.block)
        self.assertEqual(result.error, "invalid_output")
        self.assertIn(("generated_token_id", ""), result.metadata)

    def test_adapter_is_directly_callable_by_gateway(self) -> None:
        adapter = object.__new__(KananaPromptAdapter)
        adapter.model_id = "model"
        adapter.revision = "revision"
        adapter.classify = lambda text: AdapterResult(
            block=text == "차단",
            category="A1" if text == "차단" else None,
            raw_output="<UNSAFE-A1>" if text == "차단" else "<SAFE>",
            error_type=None,
            latency_ms=1.0,
            input_token_count=1,
            tokenized_input_sha256="abc",
            generated_token_id=1,
        )

        result = adapter("차단")

        self.assertTrue(result.block)
        self.assertEqual(result.category, "A1")

    def test_adapter_batch_callable_converts_results_in_order(self) -> None:
        adapter = object.__new__(KananaPromptAdapter)
        adapter.model_id = "model"
        adapter.revision = "revision"

        def classify_batch(texts):
            return tuple(
                AdapterResult(
                    block=text == "차단",
                    category="A1" if text == "차단" else None,
                    raw_output="<UNSAFE-A1>" if text == "차단" else "<SAFE>",
                    error_type=None,
                    latency_ms=2.0,
                    input_token_count=index + 1,
                    tokenized_input_sha256=f"hash-{index}",
                    generated_token_id=index,
                )
                for index, text in enumerate(texts)
            )

        adapter.classify_batch = classify_batch
        results = adapter.batch(("허용", "차단"))

        self.assertEqual([result.block for result in results], [False, True])
        self.assertEqual(results[1].category, "A1")
        self.assertIn(("input_token_count", "2"), results[1].metadata)

    def test_classify_delegates_to_one_item_batch(self) -> None:
        adapter = object.__new__(KananaPromptAdapter)
        expected = AdapterResult(
            block=False,
            category=None,
            raw_output="<SAFE>",
            error_type=None,
            latency_ms=1.0,
            input_token_count=1,
            tokenized_input_sha256="hash",
            generated_token_id=1,
        )
        calls = []

        def classify_batch(texts):
            calls.append(texts)
            return (expected,)

        adapter.classify_batch = classify_batch

        self.assertIs(adapter.classify("입력"), expected)
        self.assertEqual(calls, [("입력",)])

    def test_batch_input_rejects_string_and_non_string_item(self) -> None:
        adapter = object.__new__(KananaPromptAdapter)

        with self.assertRaisesRegex(TypeError, "sequence"):
            adapter.classify_batch("입력")
        with self.assertRaisesRegex(TypeError, "str"):
            adapter.classify_batch(("입력", 3))
        self.assertEqual(adapter.classify_batch(()), ())


if __name__ == "__main__":
    unittest.main()
