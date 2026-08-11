from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from experiments.benchmark.run_chosung_guardrail_evaluation import (
    POLICY_NAMES,
    summarize_policy_metrics,
    summarize_policy_transitions,
    write_json,
)


DEFAULT_BUDGETS = (1, 2, 4, 6, 8, 10, 12, 16)


def parse_budgets(value: str) -> tuple[int, ...]:
    try:
        budgets = tuple(sorted({int(item.strip()) for item in value.split(",")}))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("view budget은 쉼표로 구분한 정수여야 합니다.") from exc
    if not budgets or budgets[0] < 1:
        raise argparse.ArgumentTypeError("view budget은 하나 이상의 양의 정수여야 합니다.")
    return budgets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "기존 초성 후보 가드레일 예측의 prefix를 재집계해 view budget별 "
            "TPR·NRR·ΔFPR을 비교합니다."
        )
    )
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--budgets",
        type=parse_budgets,
        default=DEFAULT_BUDGETS,
        help="총 view 수 목록(기본값: 1,2,4,6,8,10,12,16)",
    )
    parser.add_argument("--bootstrap-samples", type=int, default=10_000)
    parser.add_argument("--random-seed", type=int, default=2026)
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def cap_policy_record(record: dict[str, Any], budget: int) -> dict[str, Any]:
    """한 정책 레코드를 앞쪽 view budget만 사용하는 OR 판정으로 재집계한다."""
    if budget < 1:
        raise ValueError("view budget은 1 이상이어야 합니다.")
    views = record["views"][:budget]
    if not views:
        raise ValueError("정책 레코드에 view가 없습니다.")
    errors = [view["error_type"] for view in views if view["error_type"] is not None]
    trigger = next(
        (index for index, view in enumerate(views) if view["block"] is True),
        None,
    )
    capped = dict(record)
    capped.update(
        {
            "policy_block": None if errors else trigger is not None,
            "policy_category": (
                views[trigger]["category"]
                if not errors and trigger is not None
                else None
            ),
            "policy_error": errors[0] if errors else None,
            "trigger_view_index": None if errors else trigger,
            "view_count": len(views),
            "generated_view_count": len(views) - 1,
            "model_latency_sum_ms": round(
                sum(view["latency_ms"] for view in views), 3
            ),
            "truncated": bool(record["truncated"] or len(record["views"]) > budget),
            "views": views,
        }
    )
    return capped


def summarize_costs(records: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for policy_name in POLICY_NAMES:
        items = [
            record
            for record in records
            if record["policy"] == policy_name and record["technique"] != "clean"
        ]
        result[policy_name] = {
            "mean_total_views": statistics.fmean(item["view_count"] for item in items),
            "mean_additional_views": statistics.fmean(
                item["generated_view_count"] for item in items
            ),
            "mean_model_latency_sum_ms": statistics.fmean(
                item["model_latency_sum_ms"] for item in items
            ),
        }
    return result


def summarize_budget(
    records: list[dict[str, Any]],
    budget: int,
    bootstrap_samples: int,
    random_seed: int,
) -> dict[str, Any]:
    capped = [cap_policy_record(record, budget) for record in records]
    return {
        "budget": budget,
        "policy_metrics": summarize_policy_metrics(
            capped, bootstrap_samples, random_seed
        ),
        "policy_transitions": summarize_policy_transitions(capped),
        "policy_costs": summarize_costs(capped),
    }


def compact_policy_curve(summary: dict[str, Any], policy: str) -> dict[str, Any]:
    metric_names = (
        "attack_block_rate",
        "nrr",
        "recovery_gain",
        "delta_fpr_obfuscated",
        "delta_fpr_clean",
        "generated_view_count",
        "truncated_rate",
    )
    return {
        "status": summary["status"],
        "source": summary["source"],
        "method": summary["method"],
        "policy": policy,
        "bootstrap_samples": summary["bootstrap_samples"],
        "random_seed": summary["random_seed"],
        "budgets": [
            {
                "budget": item["budget"],
                "metrics": {
                    name: item["policy_metrics"][policy].get(name)
                    for name in metric_names
                },
                "costs": item["policy_costs"][policy],
            }
            for item in summary["budgets"]
        ],
    }


def _estimate(metric: dict[str, Any]) -> str:
    estimate = metric["seed_balanced_estimate"]
    low = metric["ci95_low"]
    high = metric["ci95_high"]
    if estimate is None:
        return "N/A"
    return f"{estimate:.2%}" if low is None else f"{estimate:.2%} ({low:.2%}–{high:.2%})"


def write_report(path: Path, summary: dict[str, Any]) -> None:
    rows = []
    for item in summary["budgets"]:
        metrics = item["policy_metrics"]["segmented"]
        costs = item["policy_costs"]["segmented"]
        rows.append(
            "| "
            + " | ".join(
                [
                    str(item["budget"]),
                    _estimate(metrics["attack_block_rate"]),
                    _estimate(metrics["nrr"]),
                    _estimate(metrics["delta_fpr_obfuscated"]),
                    f'{costs["mean_total_views"]:.2f}',
                    _estimate(metrics["truncated_rate"]),
                ]
            )
            + " |"
        )
    path.write_text(
        """# 초성 segmented 정책 view budget sweep

> 상태: `PROVISIONAL_DEV_ONLY`

기존 전체 예측의 정렬된 view prefix만 재집계한다. 모델을 다시 호출하지 않는다.

| 총 view budget | 공격 block rate | NRR | ΔFPR-obfuscated | 평균 총 view | truncation rate |
|---:|---:|---:|---:|---:|---:|
"""
        + "\n".join(rows)
        + "\n\n원본 후보 순위와 OR 판정이 고정된 경우에만 이 결과를 재사용할 수 있다.\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    if args.bootstrap_samples < 0:
        raise ValueError("bootstrap samples는 0 이상이어야 합니다.")
    source_run = args.source_run.resolve()
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else source_run / "view-budget-sweep"
    )
    if output_dir.exists():
        raise SystemExit(f"출력 디렉터리가 이미 있습니다: {output_dir}")
    manifest = json.loads((source_run / "manifest.json").read_text(encoding="utf-8"))
    records = load_jsonl(source_run / "predictions.jsonl")
    max_available = max(record["view_count"] for record in records)
    if args.budgets[-1] > max_available:
        raise ValueError(
            f"요청 budget {args.budgets[-1]}이 저장된 최대 view {max_available}보다 큽니다."
        )
    output_dir.mkdir(parents=True)
    summary = {
        "status": "PROVISIONAL_DEV_ONLY",
        "source": {
            "run_id": manifest["run_id"],
            "git_commit": manifest["git"]["commit"],
            "dataset_sha256": manifest["dataset"]["sha256"],
            "candidate_generator_version": manifest["candidate_generator"]["version"],
            "model_id": manifest["model"]["model_id"],
            "model_revision": manifest["model"]["revision"],
            "source_max_views": max_available,
        },
        "method": "prefix replay; block if any retained view blocks",
        "records": len(records),
        "bootstrap_samples": args.bootstrap_samples,
        "random_seed": args.random_seed,
        "budgets": [
            summarize_budget(
                records,
                budget,
                args.bootstrap_samples,
                args.random_seed,
            )
            for budget in args.budgets
        ],
    }
    write_json(output_dir / "summary.json", summary)
    write_json(
        output_dir / "segmented_curve.json",
        compact_policy_curve(summary, "segmented"),
    )
    write_report(output_dir / "report.md", summary)
    print(json.dumps({
        "output_dir": str(output_dir),
        "source_run": manifest["run_id"],
        "budgets": list(args.budgets),
        "records": len(records),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
