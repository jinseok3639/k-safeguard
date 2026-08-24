"""JSON bridge between the static web demo and k-safeguard."""

from __future__ import annotations

import json
from importlib.metadata import PackageNotFoundError, version
from time import perf_counter_ns
from typing import Any

from k_safeguard import Gateway
from k_safeguard.normalization import NORMALIZER_VERSION
from k_safeguard.providers import TensifyInverseProvider


BRIDGE_SCHEMA_VERSION = "web-demo-analysis-v1"
MAX_INPUT_LENGTH = 1_000
PRESETS = ("safe", "experimental")


def _package_version() -> str:
    try:
        return version("k-safeguard")
    except PackageNotFoundError:  # pragma: no cover - browser wheel is installed
        return "development"


def _metadata(items: tuple[tuple[str, str], ...]) -> list[dict[str, str]]:
    return [{"key": key, "value": value} for key, value in items]


def _validate_payload(payload: object) -> tuple[str, str]:
    if not isinstance(payload, dict):
        raise TypeError("요청은 JSON object여야 합니다.")

    text = payload.get("text")
    preset = payload.get("preset", "safe")
    if not isinstance(text, str):
        raise TypeError("text는 문자열이어야 합니다.")
    if len(text) > MAX_INPUT_LENGTH:
        raise ValueError(f"입력은 {MAX_INPUT_LENGTH:,}자 이하여야 합니다.")
    if preset not in PRESETS:
        raise ValueError(f"preset은 {', '.join(PRESETS)} 중 하나여야 합니다.")
    return text, preset


def analyze_payload(payload: object) -> dict[str, Any]:
    """Run the selected demo preset and return a JSON-serializable trace."""

    text, preset = _validate_payload(payload)
    providers = ()
    if preset == "experimental":
        providers = (
            TensifyInverseProvider(
                max_candidates=8,
                min_tense_ratio=0.10,
            ),
        )

    started = perf_counter_ns()
    result = Gateway(providers=providers, max_views=10).process(text)
    duration_ms = (perf_counter_ns() - started) / 1_000_000

    return {
        "schema_version": BRIDGE_SCHEMA_VERSION,
        "package_version": _package_version(),
        "normalizer_version": NORMALIZER_VERSION,
        "preset": preset,
        "duration_ms": duration_ms,
        "input_length": len(text),
        "original": result.original,
        "normalized": result.normalized,
        "changed": result.changed,
        "has_lossy_views": result.has_lossy_views,
        "truncated": result.truncated,
        "provider_errors": list(result.provider_errors),
        "normalization": {
            "lossy": result.normalization.lossy,
            "confidence": result.normalization.confidence,
            "applied_rules": list(result.normalization.applied_rules),
            "errors": list(result.normalization.errors),
            "edits": [
                {
                    "rule_id": edit.rule_id,
                    "source_start": edit.source_start,
                    "source_end": edit.source_end,
                    "before": edit.before,
                    "after": edit.after,
                    "confidence": edit.confidence,
                    "lossy": edit.lossy,
                }
                for edit in result.normalization.edits
            ],
        },
        "views": [
            {
                "index": index,
                "text": view.text,
                "kind": view.kind,
                "provider": view.provider,
                "lossy": view.lossy,
                "confidence": view.confidence,
                "metadata": _metadata(view.metadata),
            }
            for index, view in enumerate(result.views)
        ],
    }


def analyze_json(payload_json: str) -> str:
    """Pyodide-friendly string interface."""

    if not isinstance(payload_json, str):
        raise TypeError("payload_json은 문자열이어야 합니다.")
    payload = json.loads(payload_json)
    return json.dumps(analyze_payload(payload), ensure_ascii=False)


def runtime_metadata_json() -> str:
    """Return version and capability metadata for the loading screen."""

    return json.dumps(
        {
            "schema_version": BRIDGE_SCHEMA_VERSION,
            "package_version": _package_version(),
            "normalizer_version": NORMALIZER_VERSION,
            "max_input_length": MAX_INPUT_LENGTH,
            "presets": list(PRESETS),
        },
        ensure_ascii=False,
    )
