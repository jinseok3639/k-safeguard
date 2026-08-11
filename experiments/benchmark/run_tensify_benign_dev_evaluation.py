"""정상 한국어 dev set에서 된소리 후보 activation 정책의 FPR과 비용을 비교한다."""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import random
import re
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from experiments.benchmark.adapters import AdapterResult, KananaPromptAdapter
from experiments.benchmark.run_clean_baseline import (
    DEFAULT_MODEL_HOME,
    git_metadata,
    inference_error_result,
    load_model_spec,
    percentile,
    read_spec_version,
    sha256_file,
)
from experiments.benchmark.run_normalizer_evaluation import summarize_observations
from experiments.benchmark.run_tensify_activation_sweep import tense_evidence
from experiments.benchmark.run_tensify_guardrail_evaluation import (
    aggregate_view_results,
    batched,
)
from k_safeguard import Gateway, GatewayResult
from k_safeguard.normalization import NORMALIZER_VERSION
from k_safeguard.providers import TENSIFY_CANDIDATE_VERSION, TensifyInverseProvider


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = Path(__file__).resolve().parent / "data" / "tensify_benign_dev_v1.csv"
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "results"
POLICIES = ("raw", "all", "ratio_0.10")
REQUIRED_COLUMNS = {
    "sample_id",
    "subtype",
    "text",
    "source",
    "review_status",
    "selection_reason",
}


@dataclass(frozen=True)
class BenignDevRow:
    sample_id: str
    subtype: str
    text: str
    source: str
    review_status: str
    selection_reason: str
    tense_syllables: int
    hangul_syllables: int
    tense_ratio: float

    @property
    def ratio_band(self) -> str:
        return "at_or_above_0.10" if self.tense_ratio >= 0.10 else "below_0.10"


@dataclass(frozen=True)
class PolicyPlan:
    policy: str
    gateway: GatewayResult
    generation_latency_ms: float

    @property
    def texts(self) -> tuple[str, ...]:
        return tuple(view.text for view in self.gateway.views)

    @property
    def activated(self) -> bool:
        return any(view.provider == TensifyInverseProvider.name for view in self.gateway.views)

    @property
    def provider_truncated(self) -> bool:
        candidates = [
            view for view in self.gateway.views if view.provider == TensifyInverseProvider.name
        ]
        if not candidates:
            return False
        total = int(dict(candidates[0].metadata)["total_tense_syllables"])
        return (1 << total) - 1 > len(candidates)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--model-home",
        type=Path,
        default=Path(os.environ.get("K_SAFEGUARD_MODEL_HOME", DEFAULT_MODEL_HOME)),
    )
    parser.add_argument("--run-id")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-views", type=int, default=10)
    parser.add_argument("--max-candidates", type=int, default=9)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--bootstrap-samples", type=int, default=10_000)
    parser.add_argument("--random-seed", type=int, default=2026)
    parser.add_argument("--progress-every", type=int, default=20)
    return parser.parse_args()


def normalized_run_id(value: str | None) -> str:
    run_id = value or datetime.now(timezone.utc).strftime("tensify-benign-dev-%Y%m%dT%H%M%SZ")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_id):
        raise ValueError("run-id에는 영문, 숫자, 점, 밑줄, 하이픈만 사용할 수 있습니다.")
    return run_id


def load_benign_dev(path: Path, limit: int | None = None) -> list[BenignDevRow]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"dev CSV 필수 열 누락: {', '.join(sorted(missing))}")
        source_rows = list(reader)

    seen_ids: set[str] = set()
    seen_texts: set[str] = set()
    rows: list[BenignDevRow] = []
    for line_number, source in enumerate(source_rows, start=2):
        if source.get(None):
            raise ValueError(f"{line_number}행에 헤더보다 많은 CSV 값이 있습니다.")
        values = {key: source[key].strip() for key in REQUIRED_COLUMNS}
        empty = sorted(key for key, value in values.items() if not value)
        if empty:
            raise ValueError(f"{line_number}행 필수 값 누락: {', '.join(empty)}")
        sample_id = values["sample_id"]
        text = values["text"]
        if sample_id in seen_ids:
            raise ValueError(f"중복 sample_id: {sample_id}")
        if text in seen_texts:
            raise ValueError(f"중복 text: {sample_id}")
        seen_ids.add(sample_id)
        seen_texts.add(text)
        tense_count, hangul_count, ratio = tense_evidence(text)
        if tense_count < 1:
            raise ValueError(f"된소리 음절이 없는 행: {sample_id}")
        rows.append(
            BenignDevRow(
                sample_id=sample_id,
                subtype=values["subtype"],
                text=text,
                source=values["source"],
                review_status=values["review_status"],
                selection_reason=values["selection_reason"],
                tense_syllables=tense_count,
                hangul_syllables=hangul_count,
                tense_ratio=ratio,
            )
        )
    if limit is not None:
        if limit < 1:
            raise ValueError("--limit은 1 이상이어야 합니다.")
        rows = rows[:limit]
    if not rows:
        raise ValueError("평가할 dev 행이 없습니다.")
    return rows


def make_gateways(max_views: int, max_candidates: int) -> dict[str, Gateway]:
    return {
        "raw": Gateway(max_views=max_views),
        "all": Gateway(
            providers=[TensifyInverseProvider(max_candidates=max_candidates)],
            max_views=max_views,
        ),
        "ratio_0.10": Gateway(
            providers=[
                TensifyInverseProvider(
                    max_candidates=max_candidates,
                    min_tense_ratio=0.10,
                )
            ],
            max_views=max_views,
        ),
    }


def build_policy_plan(text: str, policy: str, gateway: Gateway) -> PolicyPlan:
    if policy not in POLICIES:
        raise ValueError(f"지원하지 않는 policy: {policy}")
    started = time.perf_counter()
    result = gateway.process(text)
    return PolicyPlan(policy, result, (time.perf_counter() - started) * 1000)


def collect_unique_texts(plans: Sequence[PolicyPlan]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(text for plan in plans for text in plan.texts))


def build_record(
    row: BenignDevRow,
    plan: PolicyPlan,
    view_results: Sequence[AdapterResult],
) -> dict[str, Any]:
    aggregate = aggregate_view_results(view_results)
    return {
        "sample_id": row.sample_id,
        "label": "benign",
        "subtype": row.subtype,
        "source": row.source,
        "review_status": row.review_status,
        "selection_reason": row.selection_reason,
        "text": row.text,
        "tense_syllables": row.tense_syllables,
        "hangul_syllables": row.hangul_syllables,
        "tense_ratio": row.tense_ratio,
        "ratio_band": row.ratio_band,
        "policy": plan.policy,
        "activated": plan.activated,
        "policy_block": aggregate["block"],
        "policy_category": aggregate["category"],
        "policy_error": aggregate["error_type"],
        "trigger_view_index": aggregate["trigger_view_index"],
        "view_count": len(plan.gateway.views),
        "generated_view_count": len(plan.gateway.views) - 1,
        "candidate_generation_latency_ms": round(plan.generation_latency_ms, 3),
        "truncated": plan.gateway.truncated or plan.provider_truncated,
        "gateway_truncated": plan.gateway.truncated,
        "provider_truncated": plan.provider_truncated,
        "provider_errors": list(plan.gateway.provider_errors),
        "views": [
            {
                "index": index,
                "text": view.text,
                "kind": view.kind,
                "provider": view.provider,
                "lossy": view.lossy,
                "confidence": view.confidence,
                "metadata": dict(view.metadata),
                **result.to_dict(),
            }
            for index, (view, result) in enumerate(zip(plan.gateway.views, view_results))
        ],
    }


def valid_block(record: dict[str, Any]) -> bool | None:
    value = record["policy_block"]
    return value if record["policy_error"] is None and isinstance(value, bool) else None


def metric(
    observations: list[tuple[str, float]],
    bootstrap_samples: int,
    random_seed: int,
) -> dict[str, Any]:
    return summarize_observations(observations, bootstrap_samples, random_seed)


def summarize_policies(
    records: list[dict[str, Any]],
    bootstrap_samples: int,
    random_seed: int,
) -> dict[str, Any]:
    raw_by_id = {
        item["sample_id"]: item for item in records if item["policy"] == "raw"
    }
    output: dict[str, Any] = {}
    for policy in POLICIES:
        values: dict[str, list[tuple[str, float]]] = defaultdict(list)
        policy_records = [item for item in records if item["policy"] == policy]
        for record in policy_records:
            sample_id = record["sample_id"]
            block = valid_block(record)
            raw_block = valid_block(raw_by_id[sample_id])
            values["activation_rate"].append((sample_id, float(record["activated"])))
            values["generated_view_count"].append(
                (sample_id, float(record["generated_view_count"]))
            )
            values["view_count"].append((sample_id, float(record["view_count"])))
            values["truncated_rate"].append((sample_id, float(record["truncated"])))
            values["candidate_generation_latency_ms"].append(
                (sample_id, float(record["candidate_generation_latency_ms"]))
            )
            if block is None:
                continue
            values["fpr"].append((sample_id, float(block)))
            if raw_block is not None:
                values["delta_fpr"].append(
                    (sample_id, float(block) - float(raw_block))
                )
                values["newly_blocked_rate"].append(
                    (sample_id, float(not raw_block and block))
                )
                values["newly_allowed_rate"].append(
                    (sample_id, float(raw_block and not block))
                )
        output[policy] = {
            "rows": len(policy_records),
            "valid": sum(valid_block(item) is not None for item in policy_records),
            "errors": sum(item["policy_error"] is not None for item in policy_records),
            "view_count_p95": percentile(
                [float(item["view_count"]) for item in policy_records], 0.95
            ),
            "metrics": {
                name: metric(observations, bootstrap_samples, random_seed)
                for name, observations in sorted(values.items())
            },
        }
    return output


def summarize_transitions(records: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    by_key = {(item["sample_id"], item["policy"]): item for item in records}
    output: dict[str, dict[str, int]] = {}
    for policy in POLICIES[1:]:
        counts = {"eligible": 0, "newly_blocked": 0, "newly_allowed": 0, "unchanged": 0}
        for sample_id in sorted({item["sample_id"] for item in records}):
            raw_block = valid_block(by_key[(sample_id, "raw")])
            policy_block = valid_block(by_key[(sample_id, policy)])
            if raw_block is None or policy_block is None:
                continue
            counts["eligible"] += 1
            if not raw_block and policy_block:
                counts["newly_blocked"] += 1
            elif raw_block and not policy_block:
                counts["newly_allowed"] += 1
            else:
                counts["unchanged"] += 1
        output[policy] = counts
    return output


def summarize_groups(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[(record["policy"], record["subtype"], record["ratio_band"])].append(record)
    output: list[dict[str, Any]] = []
    for (policy, subtype, ratio_band), items in sorted(groups.items()):
        valid = [item for item in items if valid_block(item) is not None]
        output.append(
            {
                "policy": policy,
                "subtype": subtype,
                "ratio_band": ratio_band,
                "rows": len(items),
                "valid": len(valid),
                "blocked": sum(valid_block(item) is True for item in valid),
                "fpr": (
                    sum(valid_block(item) is True for item in valid) / len(valid)
                    if valid
                    else None
                ),
                "activation_rate": statistics.fmean(item["activated"] for item in items),
                "mean_views": statistics.fmean(item["view_count"] for item in items),
                "view_count_p95": percentile(
                    [float(item["view_count"]) for item in items], 0.95
                ),
                "truncated_rate": statistics.fmean(item["truncated"] for item in items),
                "errors": sum(item["policy_error"] is not None for item in items),
            }
        )
    return output


def dataset_profile(rows: list[BenignDevRow]) -> dict[str, Any]:
    subtype_counts: dict[str, int] = defaultdict(int)
    band_counts: dict[str, int] = defaultdict(int)
    review_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        subtype_counts[row.subtype] += 1
        band_counts[row.ratio_band] += 1
        review_counts[row.review_status] += 1
    return {
        "rows": len(rows),
        "subtypes": dict(sorted(subtype_counts.items())),
        "ratio_bands": dict(sorted(band_counts.items())),
        "review_statuses": dict(sorted(review_counts.items())),
        "tense_syllables": {
            "min": min(row.tense_syllables for row in rows),
            "max": max(row.tense_syllables for row in rows),
            "mean": statistics.fmean(row.tense_syllables for row in rows),
        },
        "tense_ratio": {
            "min": min(row.tense_ratio for row in rows),
            "max": max(row.tense_ratio for row in rows),
            "mean": statistics.fmean(row.tense_ratio for row in rows),
        },
    }


def estimate(metric_value: dict[str, Any] | None, *, percent: bool = True) -> str:
    if not metric_value or metric_value["seed_balanced_estimate"] is None:
        return "N/A"
    value = metric_value["seed_balanced_estimate"]
    low = metric_value["ci95_low"]
    high = metric_value["ci95_high"]
    if percent:
        return f"{value:.2%}" if low is None else f"{value:.2%} ({low:.2%}–{high:.2%})"
    return f"{value:.2f}" if low is None else f"{value:.2f} ({low:.2f}–{high:.2f})"


def write_report(path: Path, run_id: str, summary: dict[str, Any]) -> None:
    rows = []
    for policy in POLICIES:
        policy_summary = summary["policy_metrics"][policy]
        metrics = policy_summary["metrics"]
        rows.append(
            "| "
            + " | ".join(
                [
                    policy,
                    estimate(metrics.get("fpr")),
                    estimate(metrics.get("delta_fpr")),
                    estimate(metrics.get("activation_rate")),
                    estimate(metrics.get("generated_view_count"), percent=False),
                    f'{policy_summary["view_count_p95"]:.2f}',
                    estimate(metrics.get("truncated_rate")),
                    str(policy_summary["errors"]),
                ]
            )
            + " |"
        )
    transitions = summary["transitions"]
    profile = summary["dataset_profile"]
    runtime = summary["runtime"]
    report = f"""# 정상 한국어 된소리 activation dev 평가

> run ID: `{run_id}`
>
> 상태: `PROVISIONAL_DEV_ONLY`

## 결과

| 정책 | FPR | ΔFPR vs raw | activation | 평균 추가 view | view p95 | cap rate | 오류 |
|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

## 판정 전환

- `all`: 신규 차단 {transitions['all']['newly_blocked']}건 / 신규 허용 {transitions['all']['newly_allowed']}건
- `ratio_0.10`: 신규 차단 {transitions['ratio_0.10']['newly_blocked']}건 / 신규 허용 {transitions['ratio_0.10']['newly_allowed']}건

## dev set 구성

- 전체 {profile['rows']}건
- 된소리 비율 0.10 미만: {profile['ratio_bands'].get('below_0.10', 0)}건
- 된소리 비율 0.10 이상: {profile['ratio_bands'].get('at_or_above_0.10', 0)}건
- subtype: {json.dumps(profile['subtypes'], ensure_ascii=False)}
- 검수 상태: {json.dumps(profile['review_statuses'], ensure_ascii=False)}

## 실행 비용

- unique view: {runtime['unique_inferences']:,}
- batch 호출: {runtime['batch_calls']:,} (batch size {runtime['batch_size']})
- 추론 wall time: {runtime['inference_wall_seconds']:.2f}s
- 처리량: {runtime['views_per_second']:.2f} view/s

## 해석 제한

- 정책 선택 뒤 작성한 tuning-aware dev set이며 독립 locked test가 아니다.
- 문장은 프로젝트 내부 작성본이고 현재 `team_review_needed` 상태이므로 사람 검수 전 외부 성능 주장에 사용하지 않는다.
- 정상 문장만으로 FPR과 후보 비용을 진단하며 공격 탐지율은 기존 paired 평가와 함께 해석한다.
- Kanana Safeguard-Prompt 한 모델의 Prompt track 결과이며 실제 서비스 분포를 대표하지 않는다.
- 모든 후보를 한 번에 평가한 측정치로, 서비스 조기 종료 latency와는 다르다.
"""
    path.write_text(report, encoding="utf-8")


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, values: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for value in values:
            stream.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_csv(path: Path, values: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(values[0]))
        writer.writeheader()
        writer.writerows(values)


def portable_path(path: str) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(resolved)


def build_baseline(summary: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": summary["status"],
        "provenance": {
            "run_id": manifest["run_id"],
            "created_at": manifest["created_at"],
            "spec_version": manifest["spec_version"],
            "git": manifest["git"],
            "input": {
                "path": portable_path(manifest["dataset"]["path"]),
                "sha256": manifest["dataset"]["sha256"],
            },
            "model": {
                key: manifest["model"][key]
                for key in ("model_id", "revision", "dtype", "gpu_name")
            },
            "candidate_generator": manifest["candidate_generator"],
            "bootstrap_samples": manifest["runtime"]["bootstrap_samples"],
            "random_seed": manifest["runtime"]["random_seed"],
            "batch_size": manifest["runtime"]["batch_size"],
        },
        **summary,
    }


def main() -> int:
    args = parse_args()
    if min(args.max_views, args.max_candidates, args.batch_size, args.progress_every) < 1:
        raise ValueError("view/candidate/batch/progress 설정은 1 이상이어야 합니다.")
    if args.bootstrap_samples < 0:
        raise ValueError("bootstrap-samples는 0 이상이어야 합니다.")
    run_id = normalized_run_id(args.run_id)
    output_dir = args.output_root.resolve() / run_id
    if output_dir.exists():
        raise SystemExit(f"동일 run ID 결과가 이미 있습니다: {output_dir}")

    input_path = args.input.resolve()
    rows = load_benign_dev(input_path, args.limit)
    gateways = make_gateways(args.max_views, args.max_candidates)
    plans = [
        (row, build_policy_plan(row.text, policy, gateways[policy]))
        for row in rows
        for policy in POLICIES
    ]
    unique_texts = collect_unique_texts([plan for _, plan in plans])

    model_spec, installed, lock_path = load_model_spec(args.model_home.resolve())
    random.seed(args.random_seed)
    import torch

    torch.manual_seed(args.random_seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.random_seed)
    adapter = KananaPromptAdapter(
        model_path=Path(installed["path"]),
        model_id=model_spec["model_id"],
        revision=model_spec["revision"],
        dtype=model_spec["inference_dtype"],
    )

    cache: dict[str, AdapterResult] = {}
    view_errors: list[dict[str, Any]] = []
    batches = list(batched(unique_texts, args.batch_size))
    inference_started = time.perf_counter()
    for batch_index, text_batch in enumerate(batches, start=1):
        if batch_index == 1 or batch_index % args.progress_every == 0 or batch_index == len(batches):
            print(f"[{batch_index:04d}/{len(batches):04d}] inferred={len(cache):,}", flush=True)
        try:
            results = adapter.classify_batch(text_batch)
        except Exception as exc:
            results = tuple(
                inference_error_result(f"inference_error:{type(exc).__name__}")
                for _ in text_batch
            )
        for text, result in zip(text_batch, results):
            cache[text] = result
            if result.error_type is not None:
                view_errors.append(
                    {
                        "tokenized_input_sha256": result.tokenized_input_sha256,
                        "error_type": result.error_type,
                    }
                )
    inference_wall_seconds = time.perf_counter() - inference_started

    records = [
        build_record(row, plan, tuple(cache[text] for text in plan.texts))
        for row, plan in plans
    ]
    summary = {
        "status": "PROVISIONAL_DEV_ONLY",
        "dataset_profile": dataset_profile(rows),
        "policy_records": len(records),
        "view_errors": len(view_errors),
        "provider_errors": sum(bool(item["provider_errors"]) for item in records),
        "policy_metrics": summarize_policies(
            records, args.bootstrap_samples, args.random_seed
        ),
        "transitions": summarize_transitions(records),
        "subgroup_metrics": summarize_groups(records),
        "runtime": {
            "unique_inferences": len(unique_texts),
            "batch_calls": len(batches),
            "batch_size": args.batch_size,
            "inference_wall_seconds": inference_wall_seconds,
            "views_per_second": len(unique_texts) / inference_wall_seconds,
        },
        "validity_reasons": [
            "activation 정책 선택 뒤 작성한 tuning-aware dev set이며 locked test가 아님",
            "프로젝트 내부 작성 문장이 team_review_needed 상태임",
            "Kanana Safeguard-Prompt 한 모델의 Prompt track만 측정",
            "실제 서비스의 정상 입력 분포를 대표하지 않음",
        ],
    }
    output_dir.mkdir(parents=True)
    write_jsonl(output_dir / "predictions.jsonl", records)
    write_jsonl(output_dir / "errors.jsonl", view_errors)
    write_json(output_dir / "summary.json", summary)
    write_csv(output_dir / "subgroup_metrics.csv", summary["subgroup_metrics"])
    write_report(output_dir / "report.md", run_id, summary)
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "provisional_dev_only",
        "spec_version": read_spec_version(),
        "git": git_metadata(),
        "dataset": {
            "path": str(input_path),
            "sha256": sha256_file(input_path),
            "rows": len(rows),
            "label": "benign",
            "construction": "project-authored tuning-aware dev set",
            "text_visibility": "repository_unmasked",
            "review_statuses": summary["dataset_profile"]["review_statuses"],
        },
        "policies": {
            "raw": {"providers": []},
            "all": {"min_tense_syllables": 1, "min_tense_ratio": 0.0},
            "ratio_0.10": {"min_tense_syllables": 1, "min_tense_ratio": 0.10},
        },
        "candidate_generator": {
            "name": TensifyInverseProvider.name,
            "version": TENSIFY_CANDIDATE_VERSION,
            "normalizer_version": NORMALIZER_VERSION,
            "max_candidates": args.max_candidates,
            "max_views": args.max_views,
            "decision_rule": "block if any retained view blocks",
        },
        "model": adapter.runtime_metadata,
        "model_lock": {
            "path": str(lock_path),
            "sha256": sha256_file(lock_path),
            "resolved_revision": installed["resolved_revision"],
        },
        "runtime": {
            "python": sys.version,
            "platform": platform.platform(),
            "random_seed": args.random_seed,
            "bootstrap_samples": args.bootstrap_samples,
            "batch_size": args.batch_size,
            "hf_hub_offline": os.environ.get("HF_HUB_OFFLINE"),
            "transformers_offline": os.environ.get("TRANSFORMERS_OFFLINE"),
        },
        "artifacts": {
            "predictions": "predictions.jsonl",
            "errors": "errors.jsonl",
            "summary": "summary.json",
            "subgroup_metrics": "subgroup_metrics.csv",
            "report": "report.md",
            "baseline": "baseline.json",
        },
    }
    write_json(output_dir / "manifest.json", manifest)
    write_json(output_dir / "baseline.json", build_baseline(summary, manifest))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"output_dir={output_dir}")
    return 0 if not view_errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
