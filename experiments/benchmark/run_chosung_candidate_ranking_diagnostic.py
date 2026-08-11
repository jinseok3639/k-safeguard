from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from experiments.benchmark.run_chosung_lexical_diagnostic import load_priority_words
from experiments.benchmark.run_chosung_guardrail_evaluation import write_json
from experiments.benchmark.run_normalizer_evaluation import DEFAULT_INPUT, load_benchmark
from k_safeguard.chosung import (
    ChosungCandidate,
    ChosungLexicon,
    expand_korean_noun_particles,
    generate_chosung_candidates,
)


DEFAULT_PRIORITY_LEXICON = (
    Path(__file__).resolve().parent / "lexicons" / "guardrail_domain_v1.txt"
)
DEFAULT_BUDGETS = (2, 4, 6, 8, 10, 16)
STRATEGIES = ("current", "source_first", "domain_first", "few_replacements")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "저장된 초성 후보 판정과 후보 metadata를 결합해 현재 순위와 안전한 대안 "
            "휴리스틱을 비교합니다."
        )
    )
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--priority-lexicon", type=Path, default=DEFAULT_PRIORITY_LEXICON)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def candidate_features(
    candidate: ChosungCandidate,
    original_index: int,
    priority_source: str,
) -> dict[str, Any]:
    if any(replacement.partial for replacement in candidate.replacements):
        layer = "partial"
        layer_rank = 2
    elif any(
        len(replacement.segment_words) > 1
        for replacement in candidate.replacements
    ):
        layer = "segmented"
        layer_rank = 1
    else:
        layer = "direct"
        layer_rank = 0
    sources = tuple(
        source
        for replacement in candidate.replacements
        for source in replacement.segment_sources
    )
    return {
        "text": candidate.text,
        "original_index": original_index,
        "layer": layer,
        "layer_rank": layer_rank,
        "all_priority_source": bool(sources) and all(
            source == priority_source for source in sources
        ),
        "source_rank_sum": sum(
            replacement.source_rank for replacement in candidate.replacements
        ),
        "covered_initials": candidate.covered_initials,
        "replacement_count": len(candidate.replacements),
        "rank_score": candidate.rank_score,
    }


def strategy_key(strategy: str, item: dict[str, Any]) -> tuple[Any, ...]:
    feature = item["features"]
    if strategy == "current":
        return (feature["original_index"],)
    common = (feature["layer_rank"],)
    if strategy == "source_first":
        return common + (
            feature["source_rank_sum"],
            -feature["covered_initials"],
            feature["rank_score"],
            feature["text"],
        )
    if strategy == "domain_first":
        return common + (
            not feature["all_priority_source"],
            -feature["covered_initials"],
            feature["rank_score"],
            feature["text"],
        )
    if strategy == "few_replacements":
        return common + (
            feature["replacement_count"],
            -feature["covered_initials"],
            feature["source_rank_sum"],
            feature["rank_score"],
            feature["text"],
        )
    raise ValueError(f"알 수 없는 ranking strategy입니다: {strategy}")


def summarize_observations(
    observations: list[dict[str, Any]],
    budgets: tuple[int, ...] = DEFAULT_BUDGETS,
) -> dict[str, Any]:
    first_recovery_rank: Counter[str] = Counter()
    first_false_positive_rank: Counter[str] = Counter()
    recovery_layer: Counter[str] = Counter()
    for observation in observations:
        current = sorted(
            observation["candidates"],
            key=lambda item: strategy_key("current", item),
        )
        first_block = next((item for item in current if item["block"]), None)
        if observation["recovery_eligible"]:
            if first_block is None:
                first_recovery_rank["none"] += 1
            else:
                rank = str(first_block["features"]["original_index"])
                first_recovery_rank[rank] += 1
                recovery_layer[first_block["features"]["layer"]] += 1
        if observation["label"] == "benign" and not observation["raw_block"]:
            if first_block is None:
                first_false_positive_rank["none"] += 1
            else:
                first_false_positive_rank[
                    str(first_block["features"]["original_index"])
                ] += 1

    strategies: dict[str, dict[str, Any]] = {}
    for strategy in STRATEGIES:
        budget_rows = []
        for budget in budgets:
            counts: Counter[str] = Counter()
            for observation in observations:
                ordered = sorted(
                    observation["candidates"],
                    key=lambda item: strategy_key(strategy, item),
                )
                blocked = observation["raw_block"] or any(
                    item["block"] for item in ordered[: budget - 1]
                )
                label = observation["label"]
                counts[f"{label}_rows"] += 1
                counts[f"{label}_blocked"] += int(blocked)
                if observation["recovery_eligible"]:
                    counts["recovery_eligible"] += 1
                    counts["recovered"] += int(blocked)
            budget_rows.append(
                {
                    "budget": budget,
                    "attack_block_rate": (
                        counts["attack_blocked"] / counts["attack_rows"]
                    ),
                    "benign_block_rate": (
                        counts["benign_blocked"] / counts["benign_rows"]
                    ),
                    "nrr_micro": counts["recovered"] / counts["recovery_eligible"],
                    "recovered": counts["recovered"],
                    "recovery_eligible": counts["recovery_eligible"],
                }
            )
        strategies[strategy] = {"budgets": budget_rows}
    return {
        "rows": len(observations),
        "first_recovery_candidate_rank": dict(sorted(first_recovery_rank.items())),
        "first_false_positive_candidate_rank": dict(
            sorted(first_false_positive_rank.items())
        ),
        "recovery_layer": dict(sorted(recovery_layer.items())),
        "strategies": strategies,
    }


def write_report(path: Path, summary: dict[str, Any]) -> None:
    rows = []
    for strategy, result in summary["diagnostic"]["strategies"].items():
        for item in result["budgets"]:
            rows.append(
                f"| {strategy} | {item['budget']} | "
                f"{item['attack_block_rate']:.2%} | {item['nrr_micro']:.2%} | "
                f"{item['benign_block_rate']:.2%} |"
            )
    path.write_text(
        """# 초성 후보 ranking 진단

> 상태: `PROVISIONAL_DEV_ONLY`

| strategy | 총 view budget | 공격 block rate | NRR(micro) | benign block rate |
|---|---:|---:|---:|---:|
"""
        + "\n".join(rows)
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    source_run = args.source_run.resolve()
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else source_run / "candidate-ranking-diagnostic"
    )
    if output_dir.exists():
        raise SystemExit(f"출력 디렉터리가 이미 있습니다: {output_dir}")
    manifest = json.loads((source_run / "manifest.json").read_text(encoding="utf-8"))
    with (source_run / "predictions.jsonl").open(encoding="utf-8") as stream:
        records = [json.loads(line) for line in stream if line.strip()]
    segmented = {
        record["variant_id"]: record
        for record in records
        if record["policy"] == "segmented" and record["technique"] == "chosung"
    }
    clean_raw = {
        record["seed_id"]: record
        for record in records
        if record["policy"] == "raw" and record["technique"] == "clean"
    }
    rows = [
        row
        for row in load_benchmark(args.input.resolve(), None, {"chosung"})
        if row.technique == "chosung"
    ]
    config = manifest["candidate_generator"]
    priority_source = config["priority_source"]
    priority_words = expand_korean_noun_particles(
        load_priority_words(args.priority_lexicon.resolve())
    )
    try:
        from wordfreq import top_n_list
    except ImportError as exc:
        raise SystemExit("wordfreq가 필요합니다.") from exc
    lexicon = ChosungLexicon.from_sources(
        [
            (priority_source, priority_words),
            ("wordfreq:ko", top_n_list("ko", config["word_limit"])),
        ]
    )
    observations = []
    matched_candidate_lists = 0
    for row in rows:
        record = segmented[row.row_id]
        result = generate_chosung_candidates(
            row.text,
            lexicon,
            max_options_per_span=config["max_options_per_span"],
            max_candidates=config["max_candidates"],
            allow_segmentation=True,
            max_segments=config["max_segments"],
            max_options_per_segment=config["max_options_per_segment"],
        )
        stored_texts = tuple(view["text"] for view in record["views"])
        generated_texts = tuple(candidate.text for candidate in result.candidates)
        if stored_texts != generated_texts:
            raise ValueError(f"저장 후보와 재생성 후보가 다릅니다: {row.row_id}")
        matched_candidate_lists += 1
        candidates = [
            {
                "features": candidate_features(
                    candidate, index, priority_source
                ),
                "block": view["block"] is True,
            }
            for index, (candidate, view) in enumerate(
                zip(result.candidates[1:], record["views"][1:]),
                start=1,
            )
        ]
        raw_block = record["views"][0]["block"] is True
        observations.append(
            {
                "label": row.label,
                "raw_block": raw_block,
                "recovery_eligible": (
                    row.label == "attack"
                    and clean_raw[row.seed_id]["policy_block"] is True
                    and not raw_block
                ),
                "candidates": candidates,
            }
        )
    summary = {
        "status": "PROVISIONAL_DEV_ONLY",
        "source": {
            "run_id": manifest["run_id"],
            "git_commit": manifest["git"]["commit"],
            "dataset_sha256": manifest["dataset"]["sha256"],
            "candidate_generator_version": config["version"],
            "model_id": manifest["model"]["model_id"],
            "model_revision": manifest["model"]["revision"],
        },
        "matched_candidate_lists": matched_candidate_lists,
        "diagnostic": summarize_observations(observations),
        "validity_reasons": [
            "공개 개발 benchmark의 counterfactual 순위 비교이며 locked test가 아님",
            "저장된 최대 16개 후보 집합 안에서만 순서를 바꿈",
            "대안 휴리스틱 선택에 label이나 모델 판정값을 feature로 사용하지 않음",
        ],
    }
    output_dir.mkdir(parents=True)
    write_json(output_dir / "summary.json", summary)
    write_report(output_dir / "report.md", summary)
    print(json.dumps({
        "output_dir": str(output_dir),
        "rows": len(observations),
        "matched_candidate_lists": matched_candidate_lists,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
