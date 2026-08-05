from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


SAFE_TOKEN = "<SAFE>"
UNSAFE_TOKENS = {
    "<UNSAFE-A1>": "A1",
    "<UNSAFE-A2>": "A2",
}


@dataclass(frozen=True)
class AdapterResult:
    block: bool | None
    category: str | None
    raw_output: str
    error_type: str | None
    latency_ms: float
    input_token_count: int
    tokenized_input_sha256: str
    generated_token_id: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_kanana_prompt_output(raw_output: str) -> tuple[bool | None, str | None, str | None]:
    """Kanana Prompt의 첫 새 토큰을 공통 block/category/error로 변환한다."""
    normalized = raw_output.strip()
    if normalized == SAFE_TOKEN:
        return False, None, None
    if normalized in UNSAFE_TOKENS:
        return True, UNSAFE_TOKENS[normalized], None
    return None, None, "invalid_output"


def hash_token_ids(token_ids: list[int]) -> str:
    payload = json.dumps(token_ids, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def normalize_device_map(device_map: dict[Any, Any] | None) -> dict[str, str]:
    """빈 루트 모듈 키를 사람이 읽을 수 있고 PowerShell과 호환되는 값으로 바꾼다."""
    return {
        "<root>" if str(key) == "" else str(key): str(value)
        for key, value in (device_map or {}).items()
    }


class KananaPromptAdapter:
    """공식 모델 카드의 chat template과 첫 토큰 판정을 그대로 적용한다."""

    def __init__(
        self,
        model_path: Path,
        model_id: str,
        revision: str,
        dtype: str = "float16",
    ) -> None:
        import torch
        import transformers

        self._torch = torch
        self._transformers = transformers
        self.model_path = model_path.resolve()
        self.model_id = model_id
        self.revision = revision
        self.dtype_name = dtype

        dtype_value = {
            "float16": torch.float16,
            "bfloat16": torch.bfloat16,
            "float32": torch.float32,
        }.get(dtype)
        if dtype_value is None:
            raise ValueError(f"지원하지 않는 dtype: {dtype}")

        self.tokenizer = transformers.AutoTokenizer.from_pretrained(
            self.model_path,
            local_files_only=True,
        )
        self.model = transformers.AutoModelForCausalLM.from_pretrained(
            self.model_path,
            local_files_only=True,
            torch_dtype=dtype_value,
            device_map="auto",
            low_cpu_mem_usage=True,
        ).eval()

        template = self.tokenizer.chat_template or ""
        self.chat_template_sha256 = hashlib.sha256(template.encode("utf-8")).hexdigest()
        self.input_device = next(self.model.parameters()).device

    @property
    def runtime_metadata(self) -> dict[str, Any]:
        torch = self._torch
        device_map = getattr(self.model, "hf_device_map", None)
        return {
            "model_id": self.model_id,
            "revision": self.revision,
            "model_path": str(self.model_path),
            "dtype": self.dtype_name,
            "device": str(self.input_device),
            "device_map": normalize_device_map(device_map),
            "torch_version": torch.__version__,
            "transformers_version": self._transformers.__version__,
            "cuda_version": torch.version.cuda,
            "cuda_available": torch.cuda.is_available(),
            "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "chat_template_sha256": self.chat_template_sha256,
            "messages_template": [{"role": "user", "content": "{text}"}],
            "decision_rule": {
                "generated_tokens": 1,
                "safe": [SAFE_TOKEN],
                "unsafe": list(UNSAFE_TOKENS),
                "other": "invalid_output",
            },
        }

    def classify(self, text: str) -> AdapterResult:
        torch = self._torch
        started = time.perf_counter()
        messages = [{"role": "user", "content": text}]
        input_ids = self.tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            return_tensors="pt",
        )
        token_ids = [int(token) for token in input_ids[0].tolist()]
        tokenized_hash = hash_token_ids(token_ids)
        input_ids = input_ids.to(self.input_device)
        pad_token_id = self.tokenizer.pad_token_id
        if pad_token_id is None:
            pad_token_id = self.tokenizer.eos_token_id
        attention_mask = (input_ids != pad_token_id).long()

        with torch.inference_mode():
            output_ids = self.model.generate(
                input_ids,
                attention_mask=attention_mask,
                do_sample=False,
                max_new_tokens=1,
                pad_token_id=self.tokenizer.eos_token_id,
            )

        generated_token_id = int(output_ids[0][input_ids.shape[-1]].item())
        raw_output = self.tokenizer.decode(generated_token_id, skip_special_tokens=True)
        block, category, error_type = parse_kanana_prompt_output(raw_output)
        latency_ms = (time.perf_counter() - started) * 1000
        return AdapterResult(
            block=block,
            category=category,
            raw_output=raw_output,
            error_type=error_type,
            latency_ms=latency_ms,
            input_token_count=len(token_ids),
            tokenized_input_sha256=tokenized_hash,
            generated_token_id=generated_token_id,
        )
