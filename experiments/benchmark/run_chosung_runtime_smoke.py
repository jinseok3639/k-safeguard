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
from experiments.benchmark.run_chosung_lexical_diagnostic import load_priority_words
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
from k_safeguard import (
    ChosungLexicon,
    Gateway,
    GatewayEvaluation,
    expand_korean_noun_particles,
)
from k_safeguard.providers import ChosungLexiconProvider


DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "results"
DEFAULT_PRIORITY_LEXICON = (
    Path(__file__).resolve().parent / "lexicons" / "guardrail_domain_v1.txt"
)
DEFAULT_VARIANT_IDS = (
    "v_d563eb030e",  # A1, first candidate block, 16 baseline views
    "v_ad53c0beac",  # A2, first candidate block, 16 baseline views
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="초성 lossy provider의 Gateway OR·조기 종료 계약을 smoke 검증합니다."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--priority-lexicon", type=Path, default=DEFAULT_PRIORITY_LEXICON)
    parser.add_argument("--priority-source", default="guardrail-domain-v1")
    parser.add_argument("--word-limit", type=int, default=30_000)
    parser.add_argument("--max-views", type=int, default=10)
    parser.add_argument("--provider-max-candidates", type=int, default=16)
    parser.add_argument(
        "--model-home",
        type=Path,
        default=Path(os.environ.get("K_SAFEGUARD_MODEL_HOME", DEFAULT_MODEL_HOME)),
    )
    parser.add_argument("--run-id", help="생략하면 UTC 시각으로 생성합니다.")
    parser.add_argument("--variant-id", action="append", dest="variant_ids")
    parser.add_argument(
        "--require-contract",
        action="store_true",
        help="모든 fixture의 회복·판정 동등성·호출 절감을 요구합니다.",
    )
    return parser.parse_args()


def normalized_run_id(value: str | None) -> str:
    run_id = value or datetime.now(timezone.utc).strftime(
        "chosung-runtime-smoke-%Y%m%dT%H%M%SZ"
    )
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_id):
        raise ValueError("run ID에는 영문, 숫자, 점, 밑줄, 하이픈만 사용할 수 있습니다.")
    return run_id


def select_chosung_rows(
    rows: Iterable[BenchmarkRow],
    variant_ids: Iterable[str],
) -> list[BenchmarkRow]:
    by_id = {row.row_id: row for row in rows}
    requested = list(variant_ids)
    if not requested:
        raise ValueError("variant ID를 하나 이상 지정해야 합니다.")
    if len(set(requested)) != len(requested):
        raise ValueError("중복 variant ID가 있습니다.")

    selected: list[BenchmarkRow] = []
    for row_id in requested:
        row = by_id.get(row_id)
        if row is None:
            raise ValueError(f"benchmark에 variant ID가 없습니다: {row_id}")
        if row.technique != "chosung":
            raise ValueError(f"chosung variant만 지원합니다: {row_id}")
        if row.label != "attack" or row.category not in {"A1_injection", "A2_leaking"}:
            raise ValueError(f"A1/A2 공격 variant만 지원합니다: {row_id}")
        selected.append(row)
    return selected


def build_lexicon(
    priority_path: Path,
    priority_source: str,
    word_limit: int,
) -> ChosungLexicon:
    if word_limit < 1:
        raise ValueError("word limit은 1 이상이어야 합니다.")
    try:
        from wordfreq import top_n_list
    except ImportError as exc:
        raise RuntimeError(
            "wordfreq가 필요합니다: pip install -r "
            "experiments/guardrail/requirements-chosung.txt"
        ) from exc
    priority_words = expand_korean_noun_particles(load_priority_words(priority_path))
    return ChosungLexicon.from_sources(
        [
            (priority_source, priority_words),
            ("wordfreq:ko", top_n_list("ko", word_limit)),
        ]
    )


def _trace(result: GatewayEvaluation) -> list[dict[str, Any]]:
    return [
        {
            "index": item.index,
            "kind": item.view.kind,
            "text": item.view.text,
            "block": item.result.block,
            "category": item.result.category,
            "error": item.result.error,
            "raw_output": dict(item.result.metadata).get("raw_output"),
            "latency_ms": item.latency_ms,
        }
        for item in result.evaluations
    ]


def build_record(
    row: BenchmarkRow,
    full: GatewayEvaluation,
    short: GatewayEvaluation,
) -> dict[str, Any]:
    same_views = [view.text for view in full.gateway.views] == [
        view.text for view in short.gateway.views
    ]
    same_decision = (
        full.block,
        full.category,
        full.trigger_view_index,
    ) == (
        short.block,
        short.category,
        short.trigger_view_index,
    )
    raw_block = full.evaluations[0].result.block
    recovered = raw_block is False and full.block is True
    calls_saved = full.evaluated_view_count - short.evaluated_view_count
    errors = (
        list(full.classifier_errors)
        + list(short.classifier_errors)
        + list(full.gateway.provider_errors)
        + list(short.gateway.provider_errors)
    )
    return {
        "variant_id": row.row_id,
        "seed_id": row.seed_id,
        "category": "A1" if row.category == "A1_injection" else "A2",
        "intensity": row.intensity,
        "text": row.text,
        "configured_views": len(full.gateway.views),
        "candidate_views": sum(view.kind == "candidate" for view in full.gateway.views),
        "truncated": full.gateway.truncated,
        "raw_block": raw_block,
        "full_block": full.block,
        "full_category": full.category,
        "full_trigger_view_index": full.trigger_view_index,
        "full_model_calls": full.evaluated_view_count,
        "short_block": short.block,
        "short_category": short.category,
        "short_trigger_view_index": short.trigger_view_index,
        "short_model_calls": short.evaluated_view_count,
        "short_stopped_early": short.stopped_early,
        "model_calls_saved": calls_saved,
        "model_call_reduction": (
            calls_saved / full.evaluated_view_count if full.evaluated_view_count else 0.0
        ),
        "same_view_plan": same_views,
        "same_decision": same_decision,
        "recovered": recovered,
        "errors": errors,
        "full_trace": _trace(full),
        "short_trace": _trace(short),
    }


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    full_calls = sum(record["full_model_calls"] for record in records)
    short_calls = sum(record["short_model_calls"] for record in records)
    saved_calls = full_calls - short_calls
    return {
        "purpose": "lossy_provider_runtime_contract_not_performance_estimate",
        "fixtures": len(records),
        "recoveries": sum(record["recovered"] for record in records),
        "same_decisions": sum(record["same_decision"] for record in records),
        "same_view_plans": sum(record["same_view_plan"] for record in records),
        "short_circuited": sum(record["short_stopped_early"] for record in records),
        "full_model_calls": full_calls,
        "short_model_calls": short_calls,
        "model_calls_saved": saved_calls,
        "model_call_reduction": saved_calls / full_calls if full_calls else 0.0,
        "errors": sum(bool(record["errors"]) for record in records),
        "categories": {
            category: sum(record["category"] == category for record in records)
            for category in ("A1", "A2")
        },
    }


def contract_exit_code(summary: dict[str, Any], require_contract: bool) -> int:
    if summary["errors"]:
        return 2
    if require_contract:
        fixture_count = summary["fixtures"]
        required = (
            summary["recoveries"],
            summary["same_decisions"],
            summary["same_view_plans"],
            summary["short_circuited"],
        )
        if any(value != fixture_count for value in required):
            return 1
        if summary["model_calls_saved"] <= 0:
            return 1
    return 0


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> int:
    args = parse_args()
    if args.max_views < 2 or args.provider_max_candidates < 2:
        raise ValueError("max views와 provider max candidates는 2 이상이어야 합니다.")
    run_id = normalized_run_id(args.run_id)
    input_path = args.input.resolve()
    priority_path = args.priority_lexicon.resolve()
    output_dir = args.output_root.resolve() / run_id
    if output_dir.exists():
        raise SystemExit(f"동일 run ID 결과가 이미 있습니다: {output_dir}")

    variant_ids = tuple(args.variant_ids or DEFAULT_VARIANT_IDS)
    rows = select_chosung_rows(load_benchmark(input_path), variant_ids)
    lexicon = build_lexicon(priority_path, args.priority_source, args.word_limit)
    provider = ChosungLexiconProvider(
        lexicon,
        max_candidates=args.provider_max_candidates,
        allow_segmentation=True,
    )
    gateway = Gateway(providers=[provider], max_views=args.max_views)
    model_spec, installed, lock_path = load_model_spec(args.model_home.resolve())
    output_dir.mkdir(parents=True)
    adapter = KananaPromptAdapter(
        model_path=Path(installed["path"]),
        model_id=model_spec["model_id"],
        revision=model_spec["revision"],
        dtype=model_spec["inference_dtype"],
    )

    records: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        print(f"[{index:02d}/{len(rows):02d}] {row.seed_id} {row.row_id}", flush=True)
        full = gateway.evaluate(
            row.text,
            adapter,
            error_mode="allow",
            stop_on_block=False,
        )
        short = gateway.evaluate(
            row.text,
            adapter,
            error_mode="allow",
            stop_on_block=True,
        )
        records.append(build_record(row, full, short))

    summary = summarize(records)
    write_jsonl(output_dir / "predictions.jsonl", records)
    write_json(output_dir / "summary.json", summary)
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
            "candidate_provider": {
                "name": provider.name,
                "priority_lexicon": str(priority_path),
                "priority_lexicon_sha256": sha256_file(priority_path),
                "priority_source": args.priority_source,
                "word_limit": args.word_limit,
                "allow_segmentation": True,
                "provider_max_candidates": args.provider_max_candidates,
                "gateway_max_views": args.max_views,
            },
            "model": adapter.runtime_metadata,
            "model_lock": {
                "path": str(lock_path),
                "sha256": sha256_file(lock_path),
                "resolved_revision": installed["resolved_revision"],
            },
            "comparison": {
                "full": {"error_mode": "allow", "stop_on_block": False},
                "short": {"error_mode": "allow", "stop_on_block": True},
            },
        },
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    exit_code = contract_exit_code(summary, args.require_contract)
    if exit_code == 1:
        print("ERROR: lossy provider runtime contract가 충족되지 않았습니다.", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
