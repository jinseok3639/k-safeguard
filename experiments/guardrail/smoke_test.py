from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoModelForSequenceClassification, AutoTokenizer


SCRIPT_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = SCRIPT_DIR / "models.json"
DEFAULT_MODEL_HOME = Path(r"D:\local llm\guardrails")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="다운로드한 가드레일 모델을 무해 입력으로 점검합니다.")
    parser.add_argument("model_key")
    parser.add_argument(
        "--model-home",
        type=Path,
        default=Path(os.environ.get("K_SAFEGUARD_MODEL_HOME", DEFAULT_MODEL_HOME)),
    )
    parser.add_argument(
        "--gpu-memory-gib",
        type=int,
        default=13,
        help="GPU에 허용할 최대 가중치 메모리. 나머지는 CPU로 offload합니다.",
    )
    return parser.parse_args()


def load_spec(key: str) -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    matches = [model for model in manifest["models"] if model["key"] == key]
    if not matches:
        valid = ", ".join(model["key"] for model in manifest["models"])
        raise SystemExit(f"알 수 없는 model key: {key}. valid: {valid}")
    return matches[0]


def first_device(model: torch.nn.Module) -> torch.device:
    return next(model.parameters()).device


def model_kwargs(spec: dict[str, Any], offload_dir: Path, gpu_memory_gib: int) -> dict[str, Any]:
    dtype = {
        "bfloat16": torch.bfloat16,
        "float16": torch.float16,
        "float32": torch.float32,
    }[spec["inference_dtype"]]
    kwargs: dict[str, Any] = {
        "local_files_only": True,
        "torch_dtype": dtype,
        "low_cpu_mem_usage": True,
    }
    if torch.cuda.is_available():
        kwargs.update(
            device_map="auto",
            max_memory={0: f"{gpu_memory_gib}GiB", "cpu": "24GiB"},
            offload_folder=str(offload_dir),
        )
    else:
        kwargs["device_map"] = "cpu"
    return kwargs


def classify_kanana(
    model: AutoModelForCausalLM,
    tokenizer: AutoTokenizer,
    adapter: str,
) -> str:
    prompt = "주말에 읽을 만한 한국 소설을 추천해 줘."
    if adapter == "kanana_content":
        messages = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": ""},
        ]
    else:
        messages = [{"role": "user", "content": prompt}]
    input_ids = tokenizer.apply_chat_template(messages, tokenize=True, return_tensors="pt")
    input_ids = input_ids.to(first_device(model))
    attention_mask = (input_ids != tokenizer.pad_token_id).long()
    with torch.inference_mode():
        output_ids = model.generate(
            input_ids,
            attention_mask=attention_mask,
            do_sample=False,
            max_new_tokens=1,
            pad_token_id=tokenizer.eos_token_id,
        )
    return tokenizer.decode(output_ids[0][input_ids.shape[-1]], skip_special_tokens=True)


def classify_qwen(model: AutoModelForCausalLM, tokenizer: AutoTokenizer) -> str:
    messages = [{"role": "user", "content": "주말에 읽을 만한 한국 소설을 추천해 줘."}]
    text = tokenizer.apply_chat_template(messages, tokenize=False)
    inputs = tokenizer([text], return_tensors="pt").to(first_device(model))
    with torch.inference_mode():
        generated = model.generate(**inputs, do_sample=False, max_new_tokens=48)
    output_ids = generated[0][inputs.input_ids.shape[-1] :]
    return tokenizer.decode(output_ids, skip_special_tokens=True).strip()


def classify_prompt_guard(model: AutoModelForSequenceClassification, tokenizer: AutoTokenizer) -> str:
    inputs = tokenizer(
        "주말에 읽을 만한 한국 소설을 추천해 줘.",
        return_tensors="pt",
        truncation=True,
        max_length=512,
    ).to(first_device(model))
    with torch.inference_mode():
        probabilities = torch.softmax(model(**inputs).logits[0], dim=-1)
    index = int(probabilities.argmax().item())
    label = model.config.id2label[index]
    return f"{label} score={float(probabilities[index]):.6f}"


def main() -> int:
    args = parse_args()
    spec = load_spec(args.model_key)
    model_path = args.model_home.resolve() / "models" / spec["key"]
    has_weights = any(model_path.glob("*.safetensors"))
    if not (model_path / "config.json").exists() or not has_weights:
        raise SystemExit(f"모델이 없습니다: {model_path}")

    if not torch.cuda.is_available():
        print("WARNING: CUDA를 사용할 수 없어 CPU smoke test를 실행합니다.")
    else:
        print(f"gpu={torch.cuda.get_device_name(0)}")
        print(f"torch={torch.__version__} cuda={torch.version.cuda}")

    offload_dir = args.model_home.resolve() / "offload" / spec["key"]
    offload_dir.mkdir(parents=True, exist_ok=True)
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    started = time.perf_counter()

    if spec["adapter"] == "prompt_guard_classifier":
        model = AutoModelForSequenceClassification.from_pretrained(
            model_path,
            **model_kwargs(spec, offload_dir, args.gpu_memory_gib),
        ).eval()
        raw_output = classify_prompt_guard(model, tokenizer)
        valid = bool(raw_output)
    else:
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            **model_kwargs(spec, offload_dir, args.gpu_memory_gib),
        ).eval()
        if spec["adapter"].startswith("kanana_"):
            raw_output = classify_kanana(model, tokenizer, spec["adapter"])
            expected = (
                r"<SAFE>|<UNSAFE-S[1-7]>"
                if spec["adapter"] == "kanana_content"
                else r"<SAFE>|<UNSAFE-A[12]>"
            )
            valid = bool(re.fullmatch(expected, raw_output))
        else:
            raw_output = classify_qwen(model, tokenizer)
            valid = bool(re.search(r"Safety: (Safe|Unsafe|Controversial)", raw_output))

    elapsed = time.perf_counter() - started
    print(f"model_key={spec['key']}")
    print(f"revision={spec['revision']}")
    print(f"raw_output={raw_output!r}")
    print(f"valid_output={str(valid).lower()}")
    print(f"elapsed_seconds={elapsed:.2f}")
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
