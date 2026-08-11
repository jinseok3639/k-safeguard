from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from experiments.benchmark.adapters import KananaPromptAdapter
from experiments.benchmark.run_clean_baseline import (
    DEFAULT_MODEL_HOME,
    git_metadata,
    load_model_spec,
    sha256_file,
    write_json,
)
from experiments.benchmark.run_normalizer_evaluation import (
    BenchmarkRow,
    DEFAULT_INPUT,
    load_benchmark,
)
from k_safeguard import Gateway, GatewayEvaluation


DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "results"
DEFAULT_VARIANT_IDS = (
    "v_1d3f7c011a",  # A1, jamo_decompose 1.0
    "v_45200fbd03",  # A1, zwsp_inject 0.5
    "v_2dabb8eec8",  # A1, zwsp_inject 1.0
    "v_3183dd808a",  # A2, jamo_decompose 0.5
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="고정 A1/A2 회복 사례로 Gateway 런타임 계약을 smoke 검증합니다."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--model-home",
        type=Path,
        default=Path(os.environ.get("K_SAFEGUARD_MODEL_HOME", DEFAULT_MODEL_HOME)),
    )
    parser.add_argument("--run-id", help="생략하면 UTC 시각으로 생성합니다.")
    parser.add_argument(
        "--variant-id",
        action="append",
        dest="variant_ids",
        help="평가할 obfuscated variant ID. 생략하면 고정 A1/A2 회복 fixture를 사용합니다.",
    )
    parser.add_argument(
        "--require-recovery",
        action="store_true",
        help="모든 obfuscated fixture가 raw allow에서 Gateway block으로 회복되지 않으면 실패합니다.",
    )
    return parser.parse_args()


def normalized_run_id(value: str | None) -> str:
    run_id = value or datetime.now(timezone.utc).strftime("gateway-smoke-%Y%m%dT%H%M%SZ")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_id):
        raise ValueError("run ID에는 영문, 숫자, 점, 밑줄, 하이픈만 사용할 수 있습니다.")
    return run_id


def select_contract_rows(
    rows: Iterable[BenchmarkRow],
    variant_ids: Iterable[str],
) -> list[BenchmarkRow]:
    all_rows = list(rows)
    by_id = {row.row_id: row for row in all_rows}
    requested = list(variant_ids)
    if not requested:
        raise ValueError("variant ID를 하나 이상 지정해야 합니다.")
    if len(set(requested)) != len(requested):
        raise ValueError("중복 variant ID가 있습니다.")

    variants: list[BenchmarkRow] = []
    for row_id in requested:
        row = by_id.get(row_id)
        if row is None:
            raise ValueError(f"benchmark에 variant ID가 없습니다: {row_id}")
        if row.technique == "clean":
            raise ValueError(f"clean 행은 variant fixture로 지정할 수 없습니다: {row_id}")
        if row.label != "attack" or row.category not in {"A1_injection", "A2_leaking"}:
            raise ValueError(f"A1/A2 공격 variant만 지원합니다: {row_id}")
        variants.append(row)

    clean_by_seed = {
        row.seed_id: row for row in all_rows if row.technique == "clean"
    }
    selected: list[BenchmarkRow] = []
    added_clean: set[str] = set()
    for variant in variants:
        if variant.seed_id not in added_clean:
            clean = clean_by_seed.get(variant.seed_id)
            if clean is None:
                raise ValueError(f"clean pair가 없습니다: {variant.seed_id}")
            selected.append(clean)
            added_clean.add(variant.seed_id)
        selected.append(variant)
    return selected


def _metadata(result: GatewayEvaluation, index: int) -> dict[str, str]:
    return dict(result.evaluations[index].result.metadata)


def build_record(row: BenchmarkRow, result: GatewayEvaluation) -> dict[str, Any]:
    raw = result.evaluations[0]
    normalized = next(
        (item for item in result.evaluations if item.view.kind == "normalized"),
        None,
    )
    trigger_kind = (
        result.evaluations[result.trigger_view_index].view.kind
        if result.trigger_view_index is not None
        else None
    )
    return {
        "variant_id": row.row_id,
        "seed_id": row.seed_id,
        "label": row.label,
        "category": "A1" if row.category == "A1_injection" else "A2",
        "technique": row.technique,
        "intensity": row.intensity,
        "text": row.text,
        "normalizer_changed": result.gateway.changed,
        "normalizer_rules": list(result.gateway.normalization.applied_rules),
        "normalized_text": result.gateway.normalized,
        "raw_block": raw.result.block,
        "raw_category": raw.result.category,
        "raw_error": raw.result.error,
        "raw_output": _metadata(result, 0).get("raw_output"),
        "normalized_block": normalized.result.block if normalized else None,
        "normalized_category": normalized.result.category if normalized else None,
        "normalized_error": normalized.result.error if normalized else None,
        "normalized_output": (
            dict(normalized.result.metadata).get("raw_output") if normalized else None
        ),
        "gateway_block": result.block,
        "gateway_category": result.category,
        "decision_source": result.decision_source,
        "trigger_view_index": result.trigger_view_index,
        "trigger_view_kind": trigger_kind,
        "evaluated_view_count": result.evaluated_view_count,
        "classifier_errors": list(result.classifier_errors),
        "provider_errors": list(result.gateway.provider_errors),
        "recovered": raw.result.block is False and result.block is True,
    }


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    variants = [record for record in records if record["technique"] != "clean"]
    recoveries = [record for record in variants if record["recovered"]]
    errors = [
        record
        for record in records
        if record["classifier_errors"] or record["provider_errors"]
    ]
    return {
        "purpose": "runtime_contract_smoke_not_performance_estimate",
        "records": len(records),
        "independent_seeds": len({record["seed_id"] for record in records}),
        "variants": len(variants),
        "raw_blocked_variants": sum(record["raw_block"] is True for record in variants),
        "gateway_blocked_variants": sum(
            record["gateway_block"] is True for record in variants
        ),
        "recoveries": len(recoveries),
        "recovery_variant_ids": [record["variant_id"] for record in recoveries],
        "normalized_views": sum(
            record["evaluated_view_count"] > 1 for record in records
        ),
        "errors": len(errors),
        "error_variant_ids": [record["variant_id"] for record in errors],
        "categories": {
            category: {
                "records": sum(record["category"] == category for record in records),
                "recoveries": sum(
                    record["category"] == category and record["recovered"]
                    for record in records
                ),
            }
            for category in ("A1", "A2")
        },
    }


def contract_exit_code(summary: dict[str, Any], require_recovery: bool) -> int:
    if summary["errors"]:
        return 2
    if require_recovery and summary["recoveries"] != summary["variants"]:
        return 1
    return 0


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_report(path: Path, run_id: str, summary: dict[str, Any]) -> None:
    path.write_text(
        f"""# Gateway A1/A2 contract smoke

- run ID: `{run_id}`
- 목적: 런타임 계약 회귀 검증(성능 추정 아님)
- 독립 시드: {summary['independent_seeds']}
- 난독화 variant: {summary['variants']}
- raw block: {summary['raw_blocked_variants']}
- Gateway OR block: {summary['gateway_blocked_variants']}
- normalized view 회복: {summary['recoveries']}
- 오류: {summary['errors']}

전체 성능 수치는 기존 E0–E3 full run을 사용한다. 이 결과는 고정 fixture에서 raw 판정,
무손실 정규화 view와 OR 집계가 실제 모델을 통해 연결되는지만 확인한다.
""",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    args = parse_args()
    input_path = args.input.resolve()
    output_root = args.output_root.resolve()
    run_id = normalized_run_id(args.run_id)
    output_dir = output_root / run_id
    if output_dir.exists():
        raise SystemExit(f"동일 run ID 결과가 이미 있습니다: {output_dir}")

    variant_ids = tuple(args.variant_ids or DEFAULT_VARIANT_IDS)
    rows = select_contract_rows(load_benchmark(input_path), variant_ids)
    model_spec, installed, lock_path = load_model_spec(args.model_home.resolve())
    output_dir.mkdir(parents=True)
    adapter = KananaPromptAdapter(
        model_path=Path(installed["path"]),
        model_id=model_spec["model_id"],
        revision=model_spec["revision"],
        dtype=model_spec["inference_dtype"],
    )
    gateway = Gateway()

    records: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        print(f"[{index:02d}/{len(rows):02d}] {row.seed_id} {row.row_id}", flush=True)
        evaluation = gateway.evaluate(
            row.text,
            adapter,
            error_mode="allow",
            stop_on_block=False,
        )
        records.append(build_record(row, evaluation))

    summary = summarize(records)
    write_jsonl(output_dir / "predictions.jsonl", records)
    write_json(output_dir / "summary.json", summary)
    write_report(output_dir / "report.md", run_id, summary)
    write_json(
        output_dir / "manifest.json",
        {
            "schema_version": 1,
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "purpose": summary["purpose"],
            "git": git_metadata(),
            "dataset": {
                "path": str(input_path),
                "sha256": sha256_file(input_path),
                "variant_ids": list(variant_ids),
                "text_visibility": "local_unmasked",
            },
            "model": adapter.runtime_metadata,
            "model_lock": {
                "path": str(lock_path),
                "sha256": sha256_file(lock_path),
                "resolved_revision": installed["resolved_revision"],
            },
            "policy": {
                "error_mode": "allow",
                "stop_on_block": False,
                "decision": "block if original or normalized view blocks",
            },
            "artifacts": {
                "predictions": "predictions.jsonl",
                "summary": "summary.json",
                "report": "report.md",
            },
        },
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    exit_code = contract_exit_code(summary, args.require_recovery)
    if exit_code == 1:
        print(
            "ERROR: 모든 obfuscated fixture가 normalized view에서 회복되지 않았습니다.",
            file=sys.stderr,
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
