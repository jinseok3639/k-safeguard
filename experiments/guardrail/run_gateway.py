from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from experiments.benchmark.adapters import KananaPromptAdapter
from k_safeguard import Gateway, GatewayEvaluation


SCRIPT_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = SCRIPT_DIR / "models.json"
DEFAULT_MODEL_HOME = Path(r"D:\local llm\guardrails")
DEFAULT_MODEL_KEY = "kanana-prompt-2.1b"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="로컬 Kanana Prompt 모델을 k-safeguard Gateway에 연결합니다."
    )
    parser.add_argument("text", help="가드레일로 평가할 입력")
    parser.add_argument("--model-key", default=DEFAULT_MODEL_KEY)
    parser.add_argument(
        "--model-home",
        type=Path,
        default=Path(os.environ.get("K_SAFEGUARD_MODEL_HOME", DEFAULT_MODEL_HOME)),
    )
    parser.add_argument(
        "--error-mode",
        choices=("raise", "block", "allow"),
        default="raise",
    )
    parser.add_argument(
        "--all-views",
        action="store_true",
        help="첫 block 뒤에도 남은 view를 모두 평가합니다.",
    )
    return parser.parse_args()


def load_model_spec(model_key: str) -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    matches = [model for model in manifest["models"] if model["key"] == model_key]
    if not matches:
        valid = ", ".join(model["key"] for model in manifest["models"])
        raise ValueError(f"알 수 없는 model key: {model_key}. valid: {valid}")
    spec = matches[0]
    if spec["adapter"] != "kanana_prompt":
        raise ValueError(
            "현재 Gateway CLI는 kanana_prompt adapter만 지원합니다: "
            f"{model_key}={spec['adapter']}"
        )
    return spec


def evaluation_payload(result: GatewayEvaluation) -> dict[str, Any]:
    return {
        "block": result.block,
        "category": result.category,
        "decision_source": result.decision_source,
        "trigger_view_index": result.trigger_view_index,
        "stopped_early": result.stopped_early,
        "classifier_errors": list(result.classifier_errors),
        "provider_errors": list(result.gateway.provider_errors),
        "normalization": {
            "changed": result.gateway.changed,
            "applied_rules": list(result.gateway.normalization.applied_rules),
        },
        "evaluations": [
            {
                "index": item.index,
                "text": item.view.text,
                "kind": item.view.kind,
                "provider": item.view.provider,
                "lossy": item.view.lossy,
                "block": item.result.block,
                "category": item.result.category,
                "error": item.result.error,
                "metadata": dict(item.result.metadata),
                "latency_ms": item.latency_ms,
            }
            for item in result.evaluations
        ],
    }


def main() -> int:
    args = parse_args()
    try:
        spec = load_model_spec(args.model_key)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    model_path = args.model_home.resolve() / "models" / spec["key"]
    if not (model_path / "config.json").exists():
        raise SystemExit(f"모델이 없습니다: {model_path}")

    adapter = KananaPromptAdapter(
        model_path=model_path,
        model_id=spec["model_id"],
        revision=spec["revision"],
        dtype=spec["inference_dtype"],
    )
    result = Gateway().evaluate(
        args.text,
        adapter,
        error_mode=args.error_mode,
        stop_on_block=not args.all_views,
    )
    print(json.dumps(evaluation_payload(result), ensure_ascii=False, indent=2))
    if result.classifier_errors:
        return 2
    return 1 if result.block else 0


if __name__ == "__main__":
    raise SystemExit(main())
