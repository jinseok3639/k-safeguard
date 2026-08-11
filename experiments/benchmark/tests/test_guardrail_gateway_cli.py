import unittest

from experiments.guardrail.run_gateway import evaluation_payload, load_model_spec
from k_safeguard import ClassifierResult, Gateway


class GuardrailGatewayCliTest(unittest.TestCase):
    def test_loads_supported_kanana_prompt_spec(self) -> None:
        spec = load_model_spec("kanana-prompt-2.1b")

        self.assertEqual(spec["adapter"], "kanana_prompt")
        self.assertEqual(
            spec["revision"],
            "167d74d4706b236580b0e48318337c7ac6ba7848",
        )

    def test_rejects_unknown_and_unsupported_models(self) -> None:
        with self.assertRaisesRegex(ValueError, "알 수 없는 model key"):
            load_model_spec("unknown")
        with self.assertRaisesRegex(ValueError, "kanana_prompt"):
            load_model_spec("qwen3guard-gen-0.6b")

    def test_serializes_gateway_trace_for_json_output(self) -> None:
        evaluation = Gateway().evaluate(
            "안녕",
            lambda text: ClassifierResult(
                block=False,
                metadata=(("model_id", "fake"),),
            ),
        )

        payload = evaluation_payload(evaluation)

        self.assertFalse(payload["block"])
        self.assertEqual(payload["decision_source"], "no_block")
        self.assertEqual(payload["evaluations"][0]["text"], "안녕")
        self.assertEqual(payload["evaluations"][0]["metadata"], {"model_id": "fake"})


if __name__ == "__main__":
    unittest.main()
