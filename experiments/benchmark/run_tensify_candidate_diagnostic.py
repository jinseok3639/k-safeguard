"""된소리 역변형 후보의 oracle 복원율과 view 비용을 진단한다."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from k_safeguard.providers.tensify import (
    DEFAULT_TENSIFY_DIVERSIFY_FROM,
    TENSIFY_CANDIDATE_VERSION,
    TensifyInverseProvider,
)


DEFAULT_INPUT = Path("hf_repo/benchmark.jsonl")
DEFAULT_OUTPUT = Path("build/tensify_inverse_v3.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-candidates", type=int, default=9)
    parser.add_argument(
        "--diversify-from",
        type=int,
        default=DEFAULT_TENSIFY_DIVERSIFY_FROM,
    )
    return parser.parse_args()


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{line_number}행은 JSON object여야 합니다.")
            rows.append(row)
    return rows


def observe_rows(
    rows: Iterable[dict[str, Any]],
    *,
    max_candidates: int,
    diversify_from: int = DEFAULT_TENSIFY_DIVERSIFY_FROM,
) -> list[dict[str, Any]]:
    provider = TensifyInverseProvider(
        max_candidates=max_candidates,
        diversify_from=diversify_from,
    )
    observations: list[dict[str, Any]] = []
    for row in rows:
        technique = row.get("technique")
        if technique not in {"clean", "tensify"}:
            continue
        text = row.get("text")
        original = row.get("original")
        if not isinstance(text, str) or not isinstance(original, str):
            raise ValueError("benchmark text와 original은 문자열이어야 합니다.")

        proposals = list(provider.generate(text))
        candidate_texts = [proposal.text for proposal in proposals]
        exact_rank = (
            candidate_texts.index(original) + 1 if original in candidate_texts else None
        )
        total_tense_syllables = (
            int(dict(proposals[0].metadata)["total_tense_syllables"])
            if proposals
            else 0
        )
        theoretical_candidates = (1 << total_tense_syllables) - 1
        observations.append(
            {
                "id": row.get("id"),
                "seed_id": row.get("seed_id"),
                "label": row.get("label"),
                "category": row.get("category"),
                "technique": technique,
                "intensity": row.get("intensity"),
                "variant_changed": text != original,
                "candidate_count": len(proposals),
                "candidate_generated": bool(proposals),
                "total_tense_syllables": total_tense_syllables,
                "truncated": theoretical_candidates > max_candidates,
                "exact_hit": exact_rank is not None,
                "top1_exact": exact_rank == 1,
                "exact_rank": exact_rank,
            }
        )
    return observations


def summarize_group(items: list[dict[str, Any]]) -> dict[str, Any]:
    if not items:
        raise ValueError("빈 그룹은 요약할 수 없습니다.")
    ranks = [item["exact_rank"] for item in items if item["exact_rank"] is not None]
    changed = [item for item in items if item["variant_changed"]]
    return {
        "n": len(items),
        "changed_n": len(changed),
        "candidate_generation_rate": statistics.fmean(
            item["candidate_generated"] for item in items
        ),
        "exact_hit_rate": statistics.fmean(item["exact_hit"] for item in items),
        "changed_exact_hit_rate": (
            statistics.fmean(item["exact_hit"] for item in changed)
            if changed
            else None
        ),
        "top1_exact_rate": statistics.fmean(item["top1_exact"] for item in items),
        "mean_candidate_count": statistics.fmean(
            item["candidate_count"] for item in items
        ),
        "mean_tense_syllable_count": statistics.fmean(
            item["total_tense_syllables"] for item in items
        ),
        "truncation_rate": statistics.fmean(item["truncated"] for item in items),
        "median_exact_rank": statistics.median(ranks) if ranks else None,
    }


def build_summary(observations: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[str, str, float], list[dict[str, Any]]] = defaultdict(list)
    for item in observations:
        grouped[(item["technique"], item["label"], item["intensity"])].append(item)

    return {
        "overall": summarize_group(observations),
        "groups": [
            {
                "technique": technique,
                "label": label,
                "intensity": intensity,
                **summarize_group(items),
            }
            for (technique, label, intensity), items in sorted(grouped.items())
        ],
    }


def main() -> None:
    args = parse_args()
    if args.max_candidates < 1:
        raise ValueError("max-candidates는 1 이상이어야 합니다.")
    if args.diversify_from < 2:
        raise ValueError("diversify-from은 2 이상이어야 합니다.")

    observations = observe_rows(
        load_rows(args.input),
        max_candidates=args.max_candidates,
        diversify_from=args.diversify_from,
    )
    summary = build_summary(observations)
    payload = {
        "schema_version": "tensify-candidate-diagnostic-v1",
        "input": str(args.input).replace("\\", "/"),
        "candidate_generator": {
            "name": TensifyInverseProvider.name,
            "version": TENSIFY_CANDIDATE_VERSION,
            "max_candidates": args.max_candidates,
            "ordering": "legacy_descending_below_threshold_else_full_then_count_extremes_round_robin",
            "diversify_from": args.diversify_from,
        },
        "scope": {
            "techniques": ["clean", "tensify"],
            "observations": len(observations),
        },
        "summary": summary,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
