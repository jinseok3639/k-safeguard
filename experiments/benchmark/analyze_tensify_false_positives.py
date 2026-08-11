"""된소리 benign dev 결과의 raw 오탐과 후보 정책 전환을 재현 가능하게 분석한다."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from experiments.benchmark.run_clean_baseline import sha256_file


BENCHMARK_ROOT = Path(__file__).resolve().parent
DEFAULT_PREDICTIONS = (
    BENCHMARK_ROOT
    / "results"
    / "tensify-benign-dev-v1-20260811"
    / "predictions.jsonl"
)
DEFAULT_OUTPUT = BENCHMARK_ROOT / "baselines" / "tensify_false_positives_v1.json"
POLICIES = ("raw", "all", "ratio_0.10")
LEXICAL_GROUPS = {
    "instruction_terms": ("명령", "지시", "실행", "절차"),
    "model_or_prompt_terms": ("모델", "프롬프트"),
    "security_terms": ("공격", "보안", "위험", "차단", "필터", "비밀 키"),
    "safety_or_privacy_terms": ("안전", "개인정보", "접근 권한"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def load_predictions(path: Path) -> list[dict[str, Any]]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_key = {(row["sample_id"], row["policy"]): row for row in rows}
    sample_ids = {row["sample_id"] for row in rows}
    expected = {(sample_id, policy) for sample_id in sample_ids for policy in POLICIES}
    if len(by_key) != len(rows) or set(by_key) != expected:
        raise ValueError("sample_id별 raw/all/ratio_0.10 결과가 정확히 하나씩 필요합니다.")
    if any(row["policy_error"] is not None for row in rows):
        raise ValueError("오류가 포함된 run은 오탐 원인 분석에 사용할 수 없습니다.")
    return rows


def lexical_groups(text: str) -> list[str]:
    return [
        group
        for group, terms in LEXICAL_GROUPS.items()
        if any(term in text for term in terms)
    ]


def analyze(rows: list[dict[str, Any]], source_path: Path) -> dict[str, Any]:
    by_key = {(row["sample_id"], row["policy"]): row for row in rows}
    raw_rows = sorted(
        (row for row in rows if row["policy"] == "raw"),
        key=lambda row: row["sample_id"],
    )
    false_positives = []
    for raw in raw_rows:
        if raw["policy_block"] is not True:
            continue
        all_row = by_key[(raw["sample_id"], "all")]
        ratio_row = by_key[(raw["sample_id"], "ratio_0.10")]
        false_positives.append(
            {
                "sample_id": raw["sample_id"],
                "subtype": raw["subtype"],
                "text": raw["text"],
                "raw_category": raw["policy_category"],
                "tense_ratio": raw["tense_ratio"],
                "lexical_groups": lexical_groups(raw["text"]),
                "all_block": all_row["policy_block"],
                "all_trigger_view_index": all_row["trigger_view_index"],
                "ratio_0.10_activated": ratio_row["activated"],
                "ratio_0.10_block": ratio_row["policy_block"],
                "ratio_0.10_trigger_view_index": ratio_row["trigger_view_index"],
            }
        )

    policy_blocked = Counter()
    policy_transitions: dict[str, dict[str, int]] = {}
    for policy in POLICIES:
        policy_rows = [row for row in rows if row["policy"] == policy]
        policy_blocked[policy] = sum(row["policy_block"] is True for row in policy_rows)
        if policy == "raw":
            continue
        transitions = Counter()
        for raw in raw_rows:
            candidate = by_key[(raw["sample_id"], policy)]
            pair = (raw["policy_block"], candidate["policy_block"])
            transitions[
                "newly_blocked"
                if pair == (False, True)
                else "newly_allowed"
                if pair == (True, False)
                else "unchanged"
            ] += 1
        policy_transitions[policy] = dict(transitions)

    return {
        "schema_version": 1,
        "status": "PROVISIONAL_DEV_DIAGNOSTIC",
        "source": {
            "run_id": source_path.parent.name,
            "predictions_sha256": sha256_file(source_path),
            "rows": len(rows),
            "samples": len(raw_rows),
        },
        "raw_false_positive_rate": len(false_positives) / len(raw_rows),
        "raw_false_positive_count": len(false_positives),
        "raw_false_positives_by_subtype": dict(
            sorted(Counter(item["subtype"] for item in false_positives).items())
        ),
        "raw_false_positives_by_category": dict(
            sorted(Counter(item["raw_category"] for item in false_positives).items())
        ),
        "lexical_group_cooccurrence": dict(
            sorted(
                Counter(
                    group
                    for item in false_positives
                    for group in item["lexical_groups"]
                ).items()
            )
        ),
        "policy_blocked_counts": dict(policy_blocked),
        "policy_transitions_from_raw": policy_transitions,
        "false_positives": false_positives,
        "interpretation_boundary": (
            "어휘 그룹은 오탐 문장 내 동시 출현 빈도이며 인과적 trigger 추정이 아니다. "
            "분석 run 뒤 사람 검수를 완료했지만 tuning-aware dev set이므로 최종 FPR "
            "추정이나 모델 비교에 사용하지 않는다."
        ),
    }


def main() -> int:
    args = parse_args()
    source = args.predictions.resolve()
    output = args.output.resolve()
    result = analyze(load_predictions(source), source)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
