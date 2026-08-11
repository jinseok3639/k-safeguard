from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import Any, Sequence

from experiments.benchmark.adapters.kanana_prompt import AdapterResult, hash_token_ids


SAFETY_PATTERN = re.compile(r"^Safety:\s*(Safe|Controversial|Unsafe)\s*$", re.MULTILINE)
CATEGORIES_PATTERN = re.compile(r"^Categories:\s*(.+?)\s*$", re.MULTILINE)
ALLOWED_CATEGORIES = {
    "Violent",
    "Non-violent Illegal Acts",
    "Sexual Content or Sexual Acts",
    "PII",
    "Personally Identifiable Information",
    "Suicide & Self-Harm",
    "Unethical Acts",
    "Politically Sensitive Topics",
    "Copyright Violation",
    "Jailbreak",
    "None",
}


def parse_qwen3guard_output(
    raw_output: str,
    *,
    block_controversial: bool = True,
) -> tuple[bool | None, str | None, str | None]:
    """Qwen3Guard의 공식 텍스트 출력을 공통 block/category/error로 변환한다."""
    safety_match = SAFETY_PATTERN.search(raw_output.strip())
    categories_match = CATEGORIES_PATTERN.search(raw_output.strip())
    if safety_match is None or categories_match is None:
        return None, None, "invalid_output"

    safety = safety_match.group(1)
    categories = tuple(
        value.strip() for value in categories_match.group(1).split(",") if value.strip()
    )
    if not categories or any(value not in ALLOWED_CATEGORIES for value in categories):
        return None, None, "invalid_output"
    if "None" in categories and len(categories) != 1:
        return None, None, "invalid_output"

    block = safety == "Unsafe" or (block_controversial and safety == "Controversial")
    category = None if categories == ("None",) else ",".join(categories)
    return block, category, None


class Qwen3GuardGenAdapter:
    """Qwen3Guard-Gen 공식 chat template과 생성형 출력 계약을 적용한다."""

    def __init__(
        self,
        model_path: Path,
        model_id: str,
        revision: str,
        dtype: str = "bfloat16",
        *,
        block_controversial: bool = True,
        max_new_tokens: int = 48,
    ) -> None:
        import torch
        import transformers

        if max_new_tokens < 1:
            raise ValueError("max_new_tokens는 1 이상이어야 합니다.")
        dtype_value = {
            "float16": torch.float16,
            "bfloat16": torch.bfloat16,
            "float32": torch.float32,
        }.get(dtype)
        if dtype_value is None:
            raise ValueError(f"지원하지 않는 dtype: {dtype}")

        self._torch = torch
        self._transformers = transformers
        self.model_path = model_path.resolve()
        self.model_id = model_id
        self.revision = revision
        self.dtype_name = dtype
        self.block_controversial = block_controversial
        self.max_new_tokens = max_new_tokens
        self.tokenizer = transformers.AutoTokenizer.from_pretrained(
            self.model_path,
            local_files_only=True,
        )
        self.tokenizer.padding_side = "left"
        self.model = transformers.AutoModelForCausalLM.from_pretrained(
            self.model_path,
            local_files_only=True,
            torch_dtype=dtype_value,
            device_map="auto",
            low_cpu_mem_usage=True,
        ).eval()
        self.input_device = next(self.model.parameters()).device
        template = self.tokenizer.chat_template or ""
        self.chat_template_sha256 = hashlib.sha256(template.encode("utf-8")).hexdigest()

    @property
    def runtime_metadata(self) -> dict[str, Any]:
        torch = self._torch
        device_map = getattr(self.model, "hf_device_map", None) or {}
        return {
            "model_id": self.model_id,
            "revision": self.revision,
            "model_path": str(self.model_path),
            "dtype": self.dtype_name,
            "device": str(self.input_device),
            "device_map": {
                "<root>" if str(key) == "" else str(key): str(value)
                for key, value in device_map.items()
            },
            "torch_version": torch.__version__,
            "transformers_version": self._transformers.__version__,
            "cuda_version": torch.version.cuda,
            "cuda_available": torch.cuda.is_available(),
            "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "chat_template_sha256": self.chat_template_sha256,
            "padding_side": self.tokenizer.padding_side,
            "messages_template": [{"role": "user", "content": "{text}"}],
            "decision_rule": {
                "generated_tokens": self.max_new_tokens,
                "allow": ["Safe"],
                "block": ["Controversial", "Unsafe"]
                if self.block_controversial
                else ["Unsafe"],
                "other": "invalid_output",
            },
        }

    def classify_batch(self, texts: Sequence[str]) -> tuple[AdapterResult, ...]:
        if isinstance(texts, (str, bytes)):
            raise TypeError("texts는 문자열이 아닌 문자열 sequence여야 합니다.")
        text_batch = tuple(texts)
        if any(not isinstance(text, str) for text in text_batch):
            raise TypeError("batch의 모든 입력은 str이어야 합니다.")
        if not text_batch:
            return ()

        torch = self._torch
        conversations = [[{"role": "user", "content": text}] for text in text_batch]
        rendered = [
            self.tokenizer.apply_chat_template(messages, tokenize=False)
            for messages in conversations
        ]
        encoded = self.tokenizer(
            rendered,
            return_tensors="pt",
            padding=True,
            return_attention_mask=True,
        )
        token_ids_by_row = [
            [int(token) for token, included in zip(row.tolist(), mask.tolist()) if included]
            for row, mask in zip(encoded["input_ids"], encoded["attention_mask"])
        ]
        input_ids = encoded["input_ids"].to(self.input_device)
        attention_mask = encoded["attention_mask"].to(self.input_device)
        pad_token_id = self.tokenizer.pad_token_id
        if pad_token_id is None:
            pad_token_id = self.tokenizer.eos_token_id

        started = time.perf_counter()
        with torch.inference_mode():
            output_ids = self.model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                do_sample=False,
                max_new_tokens=self.max_new_tokens,
                pad_token_id=pad_token_id,
            )
        latency_ms = (time.perf_counter() - started) * 1000
        input_width = input_ids.shape[-1]
        raw_outputs = self.tokenizer.batch_decode(
            output_ids[:, input_width:],
            skip_special_tokens=True,
        )

        results: list[AdapterResult] = []
        for token_ids, raw_output in zip(token_ids_by_row, raw_outputs):
            normalized = raw_output.strip()
            block, category, error_type = parse_qwen3guard_output(
                normalized,
                block_controversial=self.block_controversial,
            )
            results.append(
                AdapterResult(
                    block=block,
                    category=category,
                    raw_output=normalized,
                    error_type=error_type,
                    latency_ms=latency_ms,
                    input_token_count=len(token_ids),
                    tokenized_input_sha256=hash_token_ids(token_ids),
                    generated_token_id=None,
                )
            )
        return tuple(results)

    def classify(self, text: str) -> AdapterResult:
        return self.classify_batch((text,))[0]
