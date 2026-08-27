from __future__ import annotations

import argparse
import gc
import json
import os
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from experiments.benchmark.adapters import KananaPromptAdapter
from experiments.benchmark.run_chosung_runtime_smoke import (
    DEFAULT_PRIORITY_LEXICON,
    DEFAULT_VARIANT_IDS,
    build_lexicon,
    select_chosung_rows,
)
from experiments.benchmark.run_clean_baseline import (
    DEFAULT_MODEL_HOME,
    git_metadata,
    load_model_spec,
    sha256_file,
    write_json,
)
from experiments.benchmark.run_normalizer_evaluation import (
    DEFAULT_INPUT,
    load_benchmark,
)
from k_safeguard import (
    ChosungLexicon,
    Gateway,
    GatewayEvaluation,
    GatewayResult,
    evaluate_gateway,
    evaluate_gateway_batch,
)
from k_safeguard.providers.chosung import ChosungLexiconProvider


DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "results"
MIB = 1024 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Kanana Prompt의 단일 view 호출과 bounded batch 추론을 비교합니다."
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
        "--batch-size",
        action="append",
        type=int,
        dest="batch_sizes",
        help="반복 지정 가능. 생략하면 2, 4, max-views를 사용합니다.",
    )
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--warmup-rounds", type=int, default=1)
    parser.add_argument(
        "--require-parity",
        action="store_true",
        help="모든 batch 판정이 단일 호출 기준선과 같지 않으면 실패합니다.",
    )
    return parser.parse_args()


def normalized_run_id(value: str | None) -> str:
    run_id = value or datetime.now(timezone.utc).strftime(
        "kanana-batch-%Y%m%dT%H%M%SZ"
    )
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_id):
        raise ValueError("run ID에는 영문, 숫자, 점, 밑줄, 하이픈만 사용할 수 있습니다.")
    return run_id


def normalized_batch_sizes(
    values: Iterable[int] | None,
    max_views: int,
) -> tuple[int, ...]:
    requested = tuple(values or (2, 4, max_views))
    if any(isinstance(value, bool) or not isinstance(value, int) for value in requested):
        raise TypeError("batch size는 int여야 합니다.")
    if any(value < 1 for value in requested):
        raise ValueError("batch size는 1 이상이어야 합니다.")
    return tuple(sorted(set(requested)))


def rotated_modes(
    modes: tuple[tuple[str, int | None], ...],
    repeat: int,
) -> tuple[tuple[str, int | None], ...]:
    if not modes:
        return ()
    offset = repeat % len(modes)
    return modes[offset:] + modes[:offset]


def evaluation_signature(result: GatewayEvaluation) -> tuple[Any, ...]:
    return (
        result.block,
        result.category,
        result.trigger_view_index,
        tuple(
            (
                item.index,
                item.view.text,
                item.result.block,
                item.result.category,
                item.result.error,
                dict(item.result.metadata).get("generated_token_id"),
                dict(item.result.metadata).get("tokenized_input_sha256"),
            )
            for item in result.evaluations
        ),
    )


def _cuda_prepare(torch: Any) -> tuple[int, int]:
    if not torch.cuda.is_available():
        return 0, 0
    gc.collect()
    torch.cuda.empty_cache()
    torch.cuda.synchronize()
    baseline_allocated = torch.cuda.memory_allocated()
    baseline_reserved = torch.cuda.memory_reserved()
    torch.cuda.reset_peak_memory_stats()
    return baseline_allocated, baseline_reserved


def _cuda_peaks(torch: Any, baseline: tuple[int, int]) -> dict[str, float | None]:
    if not torch.cuda.is_available():
        return {
            "baseline_allocated_mib": None,
            "baseline_reserved_mib": None,
            "peak_allocated_mib": None,
            "peak_reserved_mib": None,
            "incremental_peak_allocated_mib": None,
            "incremental_peak_reserved_mib": None,
        }
    torch.cuda.synchronize()
    baseline_allocated, baseline_reserved = baseline
    peak_allocated = torch.cuda.max_memory_allocated()
    peak_reserved = torch.cuda.max_memory_reserved()
    return {
        "baseline_allocated_mib": baseline_allocated / MIB,
        "baseline_reserved_mib": baseline_reserved / MIB,
        "peak_allocated_mib": peak_allocated / MIB,
        "peak_reserved_mib": peak_reserved / MIB,
        "incremental_peak_allocated_mib": max(
            0, peak_allocated - baseline_allocated
        )
        / MIB,
        "incremental_peak_reserved_mib": max(0, peak_reserved - baseline_reserved)
        / MIB,
    }


def run_mode(
    plans: tuple[GatewayResult, ...],
    adapter: KananaPromptAdapter,
    *,
    mode: str,
    batch_size: int | None,
    repeat: int,
    execution_order: int,
    baseline_signatures: tuple[tuple[Any, ...], ...] | None,
) -> tuple[dict[str, Any], tuple[tuple[Any, ...], ...]]:
    torch = adapter._torch
    baseline_memory = _cuda_prepare(torch)
    started = time.perf_counter()
    if mode == "single":
        evaluations = tuple(
            evaluate_gateway(
                plan,
                adapter,
                error_mode="allow",
                stop_on_block=False,
            )
            for plan in plans
        )
    else:
        if batch_size is None:
            raise ValueError("batch mode에는 batch size가 필요합니다.")
        evaluations = tuple(
            evaluate_gateway_batch(
                plan,
                adapter.batch,
                error_mode="allow",
                stop_on_block=False,
                batch_size=batch_size,
            )
            for plan in plans
        )
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    wall_time_ms = (time.perf_counter() - started) * 1000
    memory = _cuda_peaks(torch, baseline_memory)

    signatures = tuple(evaluation_signature(result) for result in evaluations)
    parity = baseline_signatures is None or signatures == baseline_signatures
    total_views = sum(result.evaluated_view_count for result in evaluations)
    total_calls = sum(result.classifier_call_count for result in evaluations)
    classifier_latency_ms = sum(
        call.latency_ms
        for result in evaluations
        for call in result.classifier_calls
    )
    classifier_errors = sum(
        len(result.classifier_errors) for result in evaluations
    )
    return (
        {
            "mode": mode,
            "mode_key": "single" if mode == "single" else f"batch_{batch_size}",
            "batch_size": 1 if mode == "single" else batch_size,
            "repeat": repeat,
            "execution_order": execution_order,
            "fixtures": len(evaluations),
            "evaluated_views": total_views,
            "classifier_calls": total_calls,
            "wall_time_ms": wall_time_ms,
            "classifier_latency_sum_ms": classifier_latency_ms,
            "views_per_second": (
                total_views / (wall_time_ms / 1000) if wall_time_ms else None
            ),
            "decision_parity": parity,
            "classifier_errors": classifier_errors,
            **memory,
        },
        signatures,
    )


def _median(records: list[dict[str, Any]], key: str) -> float | None:
    values = [float(record[key]) for record in records if record[key] is not None]
    return statistics.median(values) if values else None


def summarize_measurements(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_mode: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_mode.setdefault(record["mode_key"], []).append(record)
    single_records = by_mode.get("single", [])
    single_wall = _median(single_records, "wall_time_ms")
    single_calls = _median(single_records, "classifier_calls")

    modes: dict[str, Any] = {}
    for mode_key, items in by_mode.items():
        wall = _median(items, "wall_time_ms")
        calls = _median(items, "classifier_calls")
        modes[mode_key] = {
            "batch_size": items[0]["batch_size"],
            "repeats": len(items),
            "evaluated_views": items[0]["evaluated_views"],
            "classifier_calls": calls,
            "wall_time_median_ms": wall,
            "classifier_latency_sum_median_ms": _median(
                items, "classifier_latency_sum_ms"
            ),
            "views_per_second_median": _median(items, "views_per_second"),
            "incremental_peak_allocated_median_mib": _median(
                items, "incremental_peak_allocated_mib"
            ),
            "incremental_peak_reserved_median_mib": _median(
                items, "incremental_peak_reserved_mib"
            ),
            "speedup_vs_single": (
                single_wall / wall if single_wall and wall else None
            ),
            "call_reduction_vs_single": (
                1 - calls / single_calls if single_calls and calls is not None else None
            ),
            "all_decisions_match_single": all(
                item["decision_parity"] for item in items
            ),
            "classifier_errors": sum(item["classifier_errors"] for item in items),
        }
    return {
        "purpose": "local_runtime_batch_diagnostic_not_population_estimate",
        "measurements": len(records),
        "all_decisions_match_single": all(
            record["decision_parity"] for record in records
        ),
        "classifier_errors": sum(record["classifier_errors"] for record in records),
        "modes": modes,
    }


def benchmark_exit_code(summary: dict[str, Any], require_parity: bool) -> int:
    if summary["classifier_errors"]:
        return 2
    if require_parity and not summary["all_decisions_match_single"]:
        return 1
    return 0


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            stream.write("\n")


def write_report(path: Path, run_id: str, summary: dict[str, Any]) -> None:
    rows = []
    for mode_key, mode in summary["modes"].items():
        rows.append(
            "| {key} | {calls:g} | {wall:.3f} | {throughput:.3f} | {speedup:.3f} | "
            "{memory:.3f} | {parity} |".format(
                key=mode_key,
                calls=mode["classifier_calls"],
                wall=mode["wall_time_median_ms"],
                throughput=mode["views_per_second_median"],
                speedup=mode["speedup_vs_single"],
                memory=mode["incremental_peak_allocated_median_mib"] or 0.0,
                parity="yes" if mode["all_decisions_match_single"] else "no",
            )
        )
    path.write_text(
        "\n".join(
            [
                "# Kanana Prompt batch runtime diagnostic",
                "",
                f"- run ID: `{run_id}`",
                f"- 측정 수: {summary['measurements']}",
                f"- 전체 판정 일치: {summary['all_decisions_match_single']}",
                f"- classifier 오류: {summary['classifier_errors']}",
                "- 지위: 이 PC의 고정 fixture runtime 진단이며 모집단 성능 추정이 아님",
                "",
                "| mode | calls | wall median ms | views/s median | speedup | "
                "incremental peak allocated MiB | parity |",
                "|---|---:|---:|---:|---:|---:|---|",
                *rows,
                "",
                "batch는 chunk 전체를 실행하므로 latency 합계는 view trace가 아니라 "
                "classifier call trace를 사용했다.",
            ]
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    args = parse_args()
    if args.max_views < 2 or args.provider_max_candidates < 2:
        raise ValueError("max views와 provider max candidates는 2 이상이어야 합니다.")
    if args.repeats < 1 or args.warmup_rounds < 0:
        raise ValueError("repeats는 1 이상, warmup rounds는 0 이상이어야 합니다.")

    run_id = normalized_run_id(args.run_id)
    input_path = args.input.resolve()
    priority_path = args.priority_lexicon.resolve()
    output_dir = args.output_root.resolve() / run_id
    if output_dir.exists():
        raise SystemExit(f"동일 run ID 결과가 이미 있습니다: {output_dir}")

    variant_ids = tuple(args.variant_ids or DEFAULT_VARIANT_IDS)
    rows = select_chosung_rows(load_benchmark(input_path), variant_ids)
    lexicon: ChosungLexicon = build_lexicon(
        priority_path,
        args.priority_source,
        args.word_limit,
    )
    provider = ChosungLexiconProvider(
        lexicon,
        max_candidates=args.provider_max_candidates,
        allow_segmentation=True,
    )
    gateway = Gateway(providers=[provider], max_views=args.max_views)
    plans = tuple(gateway.process(row.text) for row in rows)
    batch_sizes = normalized_batch_sizes(args.batch_sizes, args.max_views)
    modes = (("single", None),) + tuple(
        ("batch", batch_size) for batch_size in batch_sizes
    )

    model_spec, installed, lock_path = load_model_spec(args.model_home.resolve())
    output_dir.mkdir(parents=True)
    adapter = KananaPromptAdapter(
        model_path=Path(installed["path"]),
        model_id=model_spec["model_id"],
        revision=model_spec["revision"],
        dtype=model_spec["inference_dtype"],
    )

    largest_plan = max(plans, key=lambda plan: len(plan.views))
    for _ in range(args.warmup_rounds):
        for _, batch_size in modes:
            size = 1 if batch_size is None else min(batch_size, len(largest_plan.views))
            adapter.classify_batch(tuple(view.text for view in largest_plan.views[:size]))

    records: list[dict[str, Any]] = []
    baseline_signatures: tuple[tuple[Any, ...], ...] | None = None
    for repeat in range(args.repeats):
        for execution_order, (mode, batch_size) in enumerate(
            rotated_modes(modes, repeat)
        ):
            print(
                f"[repeat {repeat + 1}/{args.repeats}] "
                f"{'single' if mode == 'single' else f'batch-{batch_size}'}",
                flush=True,
            )
            record, signatures = run_mode(
                plans,
                adapter,
                mode=mode,
                batch_size=batch_size,
                repeat=repeat,
                execution_order=execution_order,
                baseline_signatures=baseline_signatures,
            )
            if mode == "single" and baseline_signatures is None:
                baseline_signatures = signatures
                record["decision_parity"] = True
            records.append(record)

    summary = summarize_measurements(records)
    write_jsonl(output_dir / "measurements.jsonl", records)
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
                "text_visibility": "aggregate_only_outputs",
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
                "view_counts": [len(plan.views) for plan in plans],
            },
            "model": adapter.runtime_metadata,
            "model_lock": {
                "path": str(lock_path),
                "sha256": sha256_file(lock_path),
                "resolved_revision": installed["resolved_revision"],
            },
            "measurement": {
                "repeats": args.repeats,
                "warmup_rounds": args.warmup_rounds,
                "batch_sizes": list(batch_sizes),
                "stop_on_block": False,
                "error_mode": "allow",
                "mode_order": "rotated_per_repeat",
                "cuda_peak_method": "reset_peak_memory_stats_per_mode",
            },
        },
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    exit_code = benchmark_exit_code(summary, args.require_parity)
    if exit_code == 1:
        print("ERROR: batch 판정이 단일 호출 기준선과 다릅니다.", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
