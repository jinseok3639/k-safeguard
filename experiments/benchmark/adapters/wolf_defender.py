from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Sequence

from experiments.benchmark.adapters.kanana_prompt import AdapterResult, hash_token_ids


BENIGN_LABEL_ID = 0
INJECTION_LABEL_ID = 1
MAX_LENGTH = 2048


def parse_wolf_defender_label(label_id: int) -> tuple[bool | None, str | None, str | None]:
    """Wolf Defender의 공개 이진 라벨 계약을 공통 판정으로 변환한다."""
    if label_id == BENIGN_LABEL_ID:
        return False, None, None
    if label_id == INJECTION_LABEL_ID:
        return True, "prompt_injection", None
    return None, None, "invalid_output"


def _load_tokenizer(transformers: Any, model_path: Path) -> tuple[Any, str]:
    """Transformers 4.x에서도 5.x의 TokenizersBackend 저장 형식을 읽는다."""
    config_path = model_path / "tokenizer_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("tokenizer_class") != "TokenizersBackend":
        return (
            transformers.AutoTokenizer.from_pretrained(model_path, local_files_only=True),
            "auto",
        )
    tokenizer = transformers.PreTrainedTokenizerFast(
        tokenizer_file=str(model_path / "tokenizer.json"),
        bos_token=config["bos_token"],
        eos_token=config["eos_token"],
        cls_token=config["cls_token"],
        sep_token=config["sep_token"],
        mask_token=config["mask_token"],
        pad_token=config["pad_token"],
        unk_token=config["unk_token"],
        model_max_length=int(config["model_max_length"]),
        padding_side=config.get("padding_side", "right"),
    )
    return tokenizer, "pretrained_fast_compat"


class WolfDefenderAdapter:
    """Wolf Defender의 argmax 이진 분류를 벤치마크 결과 계약으로 변환한다."""

    def __init__(
        self,
        model_path: Path,
        model_id: str,
        revision: str,
        dtype: str = "float32",
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

        self.tokenizer, self.tokenizer_loader = _load_tokenizer(
            transformers,
            self.model_path,
        )
        self.model = transformers.AutoModelForSequenceClassification.from_pretrained(
            self.model_path,
            local_files_only=True,
            torch_dtype=dtype_value,
            device_map="auto",
            low_cpu_mem_usage=True,
        ).eval()
        if self.model.config.num_labels != 2:
            raise ValueError(f"Wolf Defender는 2개 라벨이어야 합니다: {self.model.config.num_labels}")
        self.input_device = next(self.model.parameters()).device
        tokenizer_payload = (self.model_path / "tokenizer.json").read_bytes()
        self.tokenizer_sha256 = hashlib.sha256(tokenizer_payload).hexdigest()

    @property
    def runtime_metadata(self) -> dict[str, Any]:
        torch = self._torch
        return {
            "model_id": self.model_id,
            "revision": self.revision,
            "model_path": str(self.model_path),
            "dtype": self.dtype_name,
            "device": str(self.input_device),
            "torch_version": torch.__version__,
            "transformers_version": self._transformers.__version__,
            "cuda_version": torch.version.cuda,
            "cuda_available": torch.cuda.is_available(),
            "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "tokenizer_loader": self.tokenizer_loader,
            "tokenizer_sha256": self.tokenizer_sha256,
            "max_length": MAX_LENGTH,
            "decision_rule": {
                "method": "argmax",
                "benign_label_id": BENIGN_LABEL_ID,
                "injection_label_id": INJECTION_LABEL_ID,
                "threshold_tuning": False,
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

        started = time.perf_counter()
        encoded = self.tokenizer(
            text_batch,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=MAX_LENGTH,
        )
        input_ids = encoded["input_ids"]
        attention_mask = encoded["attention_mask"]
        token_ids_by_row = [
            [int(token) for token, included in zip(row.tolist(), mask.tolist()) if included]
            for row, mask in zip(input_ids, attention_mask)
        ]
        inputs = {key: value.to(self.input_device) for key, value in encoded.items()}
        with self._torch.inference_mode():
            probabilities = self._torch.softmax(self.model(**inputs).logits, dim=-1)
        latency_ms = (time.perf_counter() - started) * 1000

        results: list[AdapterResult] = []
        for token_ids, row in zip(token_ids_by_row, probabilities):
            label_id = int(row.argmax().item())
            score = float(row[label_id].item())
            block, category, error_type = parse_wolf_defender_label(label_id)
            results.append(
                AdapterResult(
                    block=block,
                    category=category,
                    raw_output=f"LABEL_{label_id} score={score:.6f}",
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
