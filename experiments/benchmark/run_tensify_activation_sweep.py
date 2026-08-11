"""저장된 paired 판정에서 된소리 후보 activation 규칙을 재집계한다."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from experiments.benchmark.run_tensify_guardrail_evaluation import (
    summarize_obfuscated_groups,
    summarize_policy_metrics,
    summarize_transition,
)
from experiments.benchmark.run_clean_baseline import git_metadata
from k_safeguard.providers import TENSIFY_CANDIDATE_VERSION


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_RUN = (
    Path(__file__).resolve().parent / "results" / "tensify-impact-v1-20260811"
)
DEFAULT_OUTPUT = (
    Path(__file__).resolve().parent
    / "baselines"
    / "tensify_activation_sweep_v1.json"
)
DEFAULT_REPORT = Path(__file__).resolve().parent / "TENSIFY_ACTIVATION_SWEEP.md"
_HANGUL_BASE = 0xAC00
_HANGUL_END = 0xD7A3
_TENSE_INITIALS = {1, 4, 8, 10, 13}


@dataclass(frozen=True)
class ActivationPolicy:
    name: str
    min_tense_syllables: int
    min_tense_ratio: float

    def enabled(self, tense_syllables: int, tense_ratio: float) -> bool:
        return (
            tense_syllables >= self.min_tense_syllables
            and tense_ratio >= self.min_tense_ratio
        )


POLICIES = (
    ActivationPolicy("all", 1, 0.0),
    ActivationPolicy("count_2", 2, 0.0),
    ActivationPolicy("count_3", 3, 0.0),
    ActivationPolicy("count_4", 4, 0.0),
    ActivationPolicy("ratio_0.10", 1, 0.10),
    ActivationPolicy("ratio_0.20", 1, 0.20),
    ActivationPolicy("count_2_ratio_0.10", 2, 0.10),
    ActivationPolicy("count_3_ratio_0.10", 3, 0.10),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, default=DEFAULT_SOURCE_RUN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--bootstrap-samples", type=int, default=10_000)
    parser.add_argument("--random-seed", type=int, default=2026)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def tense_evidence(text: str) -> tuple[int, int, float]:
    if not isinstance(text, str):
        raise TypeError("text는 str이어야 합니다.")
    hangul_syllables = 0
    tense_syllables = 0
    for char in text:
        code = ord(char)
        if not _HANGUL_BASE <= code <= _HANGUL_END:
            continue
        hangul_syllables += 1
        initial = (code - _HANGUL_BASE) // (21 * 28)
        tense_syllables += initial in _TENSE_INITIALS
    ratio = tense_syllables / hangul_syllables if hangul_syllables else 0.0
    return tense_syllables, hangul_syllables, ratio


def validate_source_records(records: list[dict[str, Any]]) -> None:
    keys: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        key = (record["variant_id"], record["policy"])
        if key in keys:
            raise ValueError(f"중복 source record: {key}")
        keys[key] = record
    variant_ids = {record["variant_id"] for record in records}
    for variant_id in variant_ids:
        raw = keys.get((variant_id, "raw"))
        inverse = keys.get((variant_id, "inverse"))
        if raw is None or inverse is None:
            raise ValueError(f"raw/inverse pair 누락: {variant_id}")
        if raw["policy_error"] is not None or inverse["policy_error"] is not None:
            raise ValueError(f"오류가 있는 source pair: {variant_id}")
        raw_views = {view["text"] for view in raw["views"]}
        inverse_views = {view["text"] for view in inverse["views"]}
        if not raw_views <= inverse_views:
            raise ValueError(f"raw view가 inverse에 보존되지 않음: {variant_id}")


def apply_policy(
    records: list[dict[str, Any]],
    policy: ActivationPolicy,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw_by_variant = {
        record["variant_id"]: record
        for record in records
        if record["policy"] == "raw"
    }
    selected: list[dict[str, Any]] = list(raw_by_variant.values())
    activation_rows: list[dict[str, Any]] = []
    for inverse in (record for record in records if record["policy"] == "inverse"):
        text = inverse["views"][0]["text"]
        tense_count, hangul_count, ratio = tense_evidence(text)
        enabled = policy.enabled(tense_count, ratio)
        source = inverse if enabled else raw_by_variant[inverse["variant_id"]]
        chosen = copy.deepcopy(source)
        chosen["policy"] = "inverse"
        chosen["activation"] = {
            "policy": policy.name,
            "enabled": enabled,
            "tense_syllables": tense_count,
            "hangul_syllables": hangul_count,
            "tense_ratio": ratio,
        }
        selected.append(chosen)
        activation_rows.append(
            {
                "seed_id": inverse["seed_id"],
                "label": inverse["label"],
                "category": inverse["category"],
                "technique": inverse["technique"],
                "intensity": inverse["intensity"],
                "enabled": enabled,
            }
        )
    return selected, activation_rows


def summarize_activation(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, float], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["label"], row["technique"], row["intensity"])].append(row)
    return [
        {
            "label": label,
            "technique": technique,
            "intensity": intensity,
            "rows": len(items),
            "activated": sum(item["enabled"] for item in items),
            "activation_rate": sum(item["enabled"] for item in items) / len(items),
        }
        for (label, technique, intensity), items in sorted(groups.items())
    ]


def activation_rate(
    groups: list[dict[str, Any]],
    *,
    label: str,
    technique: str,
    intensity: float | None = None,
) -> float:
    selected = [
        group
        for group in groups
        if group["label"] == label
        and group["technique"] == technique
        and (intensity is None or group["intensity"] == intensity)
    ]
    rows = sum(group["rows"] for group in selected)
    return sum(group["activated"] for group in selected) / rows if rows else 0.0


def evaluate_policy(
    records: list[dict[str, Any]],
    policy: ActivationPolicy,
    bootstrap_samples: int,
    random_seed: int,
) -> dict[str, Any]:
    selected, activation_rows = apply_policy(records, policy)
    metrics = summarize_policy_metrics(
        selected, bootstrap_samples, random_seed
    )["inverse"]
    groups = summarize_activation(activation_rows)
    return {
        "policy": asdict(policy),
        "metrics": metrics,
        "obfuscated_groups": summarize_obfuscated_groups(
            selected, bootstrap_samples, random_seed
        ),
        "transition": summarize_transition(selected),
        "activation": {
            "groups": groups,
            "attack_obfuscated": activation_rate(
                groups, label="attack", technique="tensify"
            ),
            "benign_obfuscated": activation_rate(
                groups, label="benign", technique="tensify"
            ),
            "benign_clean": activation_rate(
                groups, label="benign", technique="clean"
            ),
        },
    }


def select_recommended_strategy(strategies: list[dict[str, Any]]) -> dict[str, Any]:
    if not strategies:
        raise ValueError("strategy가 비어 있습니다.")
    baseline = next(
        (item for item in strategies if item["policy"]["name"] == "all"),
        None,
    )
    if baseline is None:
        raise ValueError("all 기준 정책이 없습니다.")

    def estimate(item: dict[str, Any], metric: str) -> float:
        value = item["metrics"][metric]["seed_balanced_estimate"]
        if value is None:
            raise ValueError(f"{item['policy']['name']}의 {metric}이 없습니다.")
        return float(value)

    baseline_nrr = estimate(baseline, "nrr")
    baseline_obf = estimate(baseline, "delta_fpr_obfuscated")
    baseline_clean = estimate(baseline, "delta_fpr_clean")
    eligible = [
        item
        for item in strategies
        if estimate(item, "nrr") >= baseline_nrr
        and estimate(item, "delta_fpr_obfuscated") <= baseline_obf
        and estimate(item, "delta_fpr_clean") <= baseline_clean
    ]
    if not eligible:
        raise ValueError("기준 성능을 보존하는 activation 정책이 없습니다.")
    return min(
        eligible,
        key=lambda item: (
            item["activation"]["benign_clean"],
            -item["activation"]["attack_obfuscated"],
            estimate(item, "generated_view_count"),
            item["policy"]["name"],
        ),
    )


def _estimate(metric: dict[str, Any] | None) -> str:
    if not metric or metric["seed_balanced_estimate"] is None:
        return "N/A"
    return f'{metric["seed_balanced_estimate"]:.2%}'


def _number(metric: dict[str, Any] | None) -> str:
    if not metric or metric["seed_balanced_estimate"] is None:
        return "N/A"
    return f'{metric["seed_balanced_estimate"]:.2f}'


def write_report(path: Path, payload: dict[str, Any]) -> None:
    rows = []
    for item in payload["strategies"]:
        metrics = item["metrics"]
        activation = item["activation"]
        policy = item["policy"]
        rows.append(
            "| "
            + " | ".join(
                [
                    policy["name"],
                    str(policy["min_tense_syllables"]),
                    f'{policy["min_tense_ratio"]:.0%}',
                    _estimate(metrics.get("nrr")),
                    _estimate(metrics.get("recovery_gain")),
                    _estimate(metrics.get("delta_fpr_obfuscated")),
                    _estimate(metrics.get("delta_fpr_clean")),
                    _number(metrics.get("generated_view_count")),
                    f'{activation["attack_obfuscated"]:.2%}',
                    f'{activation["benign_clean"]:.2%}',
                ]
            )
            + " |"
        )
    report = f"""# 된소리 후보 activation 정책 sweep

> source run: `{payload['provenance']['source_run_id']}`
>
> 상태: `PROVISIONAL_DEV_ONLY`

## 결과

| 정책 | 최소 경음 수 | 최소 비율 | NRR | Recovery Gain | ΔFPR-obf | ΔFPR-clean | 평균 추가 view | attack 변형 활성화 | clean benign 활성화 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

## 개발 후보

`{payload['recommended_policy']}`를 다음 dev-set 검증 후보로 선택한다. `all`의 NRR과 두 ΔFPR을
악화시키지 않는 정책 중 clean benign 활성화율을 최소화하고, 동률이면 attack 변형 활성화율이 높은
정책을 우선했다. 이 선택은 개발셋 결과를 사용했으므로 패키지 기본값을 변경하지 않는다.

## 해석 제한

- 저장된 동일 model view 판정을 재집계했으며 새 모델 추론은 수행하지 않았다.
- activation 규칙 자체는 입력의 경음 수·비율만 사용하지만, 정책 선택에는 이 개발셋 결과를 사용한다.
- 별도 정상 된소리·구어체 dev/locked set 검증 전에는 기본값으로 승격하지 않는다.
"""
    path.write_text(report, encoding="utf-8")


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    if args.bootstrap_samples < 0:
        raise ValueError("bootstrap-samples는 0 이상이어야 합니다.")
    source_dir = args.source_run.resolve()
    predictions_path = source_dir / "predictions.jsonl"
    manifest_path = source_dir / "manifest.json"
    records = load_jsonl(predictions_path)
    validate_source_records(records)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    strategies = [
        evaluate_policy(records, policy, args.bootstrap_samples, args.random_seed)
        for policy in POLICIES
    ]
    recommended = select_recommended_strategy(strategies)
    payload = {
        "status": "PROVISIONAL_DEV_ONLY",
        "provenance": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "git": git_metadata(),
            "source_run_id": manifest["run_id"],
            "source_git": manifest["git"],
            "source_predictions_sha256": sha256_file(predictions_path),
            "source_model": {
                "model_id": manifest["model"]["model_id"],
                "revision": manifest["model"]["revision"],
            },
            "source_candidate_generator": manifest["candidate_generator"],
            "activation_provider_version": TENSIFY_CANDIDATE_VERSION,
            "bootstrap_samples": args.bootstrap_samples,
            "random_seed": args.random_seed,
        },
        "source_rows": len(records),
        "selection_rule": (
            "preserve all-policy NRR and both delta-FPR estimates; then minimize "
            "clean-benign activation, maximize attack-obfuscated activation, and "
            "minimize generated views"
        ),
        "recommended_policy": recommended["policy"]["name"],
        "strategies": strategies,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, payload)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_report(args.report, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"output={args.output.resolve()}")
    print(f"report={args.report.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
