from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any

from experiments.benchmark.run_clean_baseline import sha256_file
from experiments.benchmark.run_normalizer_evaluation import DEFAULT_INPUT, load_benchmark
from k_safeguard.chosung import (
    CHOSUNG_CANDIDATE_VERSION,
    ChosungLexicon,
    expand_korean_noun_particles,
    generate_chosung_candidates,
)
from k_safeguard.normalization import normalize_korean


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ERROR_TAXONOMY_VERSION = "chosung-error-v1"
OUTCOME_CANDIDATE_NOT_GENERATED = "candidate_not_generated"
OUTCOME_OVER_RESTORATION = "over_restoration"
OUTCOME_TARGET_NOT_IN_CANDIDATES = "target_not_in_candidates"
OUTCOME_RANKING_ERROR = "ranking_error"
OUTCOME_SUCCESS = "success"
OUTCOME_ORDER = (
    OUTCOME_CANDIDATE_NOT_GENERATED,
    OUTCOME_OVER_RESTORATION,
    OUTCOME_TARGET_NOT_IN_CANDIDATES,
    OUTCOME_RANKING_ERROR,
    OUTCOME_SUCCESS,
)
OUTCOME_DEFINITIONS = {
    OUTCOME_CANDIDATE_NOT_GENERATED: "복원 후보가 하나도 생성되지 않음",
    OUTCOME_OVER_RESTORATION: (
        "후보는 생성됐지만 정답 초성 위치를 하나도 복원하지 못함; 실제 FPR이 아닌 합성 데이터 proxy"
    ),
    OUTCOME_TARGET_NOT_IN_CANDIDATES: "일부 초성은 복원했지만 정답 문장이 후보 집합에 없음",
    OUTCOME_RANKING_ERROR: "정답 문장이 후보 집합에는 있지만 첫 번째 복원 후보가 아님",
    OUTCOME_SUCCESS: "첫 번째 복원 후보가 정답 문장과 일치",
}


@dataclass(frozen=True)
class DiagnosticObservation:
    label: str
    category: str
    intensity: float
    generated: bool
    candidate_count: int
    exact_hit: bool
    top1_exact: bool
    initial_count: int
    best_initial_recall: float
    truncated: bool
    row_id: str | None = None
    seed_id: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="wordfreq 기반 초성 복원 후보의 어휘 coverage를 개발용으로 진단합니다."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--word-limit", type=int, default=30_000)
    parser.add_argument("--max-candidates", type=int, default=16)
    parser.add_argument("--max-options-per-span", type=int, default=3)
    parser.add_argument("--min-initials", type=int, default=3)
    parser.add_argument("--limit-seeds", type=int)
    parser.add_argument("--examples-per-outcome", type=int, default=10)
    parser.add_argument(
        "--priority-lexicon",
        type=Path,
        help="wordfreq보다 먼저 검색할 줄 단위 사용자·도메인 사전",
    )
    parser.add_argument("--priority-source", default="domain")
    parser.add_argument("--expand-priority-particles", action="store_true")
    parser.add_argument("--allow-segmentation", action="store_true")
    parser.add_argument("--max-segments", type=int, default=2)
    parser.add_argument("--max-options-per-segment", type=int, default=1)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def _initial_positions(text: str) -> list[int]:
    return [index for index, char in enumerate(text) if 0x3131 <= ord(char) <= 0x314E]


def observe_row(
    variant: str,
    original: str,
    label: str,
    category: str,
    intensity: float,
    lexicon: ChosungLexicon,
    *,
    min_initials: int,
    max_options_per_span: int,
    max_candidates: int,
    allow_segmentation: bool = False,
    max_segments: int = 2,
    max_options_per_segment: int = 1,
    row_id: str | None = None,
    seed_id: str | None = None,
) -> DiagnosticObservation:
    exact_normalized = normalize_korean(variant).text
    result = generate_chosung_candidates(
        exact_normalized,
        lexicon,
        min_initials=min_initials,
        max_options_per_span=max_options_per_span,
        max_candidates=max_candidates,
        allow_segmentation=allow_segmentation,
        max_segments=max_segments,
        max_options_per_segment=max_options_per_segment,
    )
    expanded = result.candidates[1:]
    initial_positions = _initial_positions(exact_normalized)
    recalls = []
    for candidate in expanded:
        correct = sum(
            index < len(candidate.text)
            and index < len(original)
            and candidate.text[index] == original[index]
            for index in initial_positions
        )
        recalls.append(correct / len(initial_positions) if initial_positions else 0.0)
    return DiagnosticObservation(
        label=label,
        category=category,
        intensity=intensity,
        generated=bool(expanded),
        candidate_count=len(expanded),
        exact_hit=any(candidate.text == original for candidate in expanded),
        top1_exact=bool(expanded) and expanded[0].text == original,
        initial_count=len(initial_positions),
        best_initial_recall=max(recalls, default=0.0),
        truncated=result.truncated,
        row_id=row_id,
        seed_id=seed_id,
    )


def classify_observation(observation: DiagnosticObservation) -> str:
    """진단 결과를 상호 배타적인 초성 복원 outcome으로 분류한다."""

    if not observation.generated:
        return OUTCOME_CANDIDATE_NOT_GENERATED
    if observation.exact_hit:
        if observation.top1_exact:
            return OUTCOME_SUCCESS
        return OUTCOME_RANKING_ERROR
    if observation.best_initial_recall == 0.0:
        return OUTCOME_OVER_RESTORATION
    return OUTCOME_TARGET_NOT_IN_CANDIDATES


def _aggregate(items: list[DiagnosticObservation]) -> dict[str, Any]:
    if not items:
        return {
            "rows": 0,
            "candidate_generation_rate": None,
            "exact_hit_rate": None,
            "top1_exact_rate": None,
            "mean_best_initial_recall": None,
            "mean_candidate_count": None,
            "truncated_rate": None,
        }
    return {
        "rows": len(items),
        "candidate_generation_rate": statistics.fmean(item.generated for item in items),
        "exact_hit_rate": statistics.fmean(item.exact_hit for item in items),
        "top1_exact_rate": statistics.fmean(item.top1_exact for item in items),
        "mean_best_initial_recall": statistics.fmean(
            item.best_initial_recall for item in items
        ),
        "mean_candidate_count": statistics.fmean(item.candidate_count for item in items),
        "truncated_rate": statistics.fmean(item.truncated for item in items),
    }


def summarize(observations: list[DiagnosticObservation]) -> dict[str, Any]:
    groups: dict[str, list[DiagnosticObservation]] = {"overall": observations}
    for label in sorted({item.label for item in observations}):
        groups[f"label:{label}"] = [item for item in observations if item.label == label]
    for intensity in sorted({item.intensity for item in observations}):
        groups[f"intensity:{intensity:g}"] = [
            item for item in observations if item.intensity == intensity
        ]
    return {name: _aggregate(items) for name, items in groups.items()}


def _outcome_aggregate(items: list[DiagnosticObservation]) -> dict[str, Any]:
    counts = {outcome: 0 for outcome in OUTCOME_ORDER}
    for item in items:
        counts[classify_observation(item)] += 1
    denominator = len(items)
    return {
        "rows": denominator,
        "counts": counts,
        "rates": {
            outcome: counts[outcome] / denominator if denominator else None
            for outcome in OUTCOME_ORDER
        },
    }


def summarize_outcomes(observations: list[DiagnosticObservation]) -> dict[str, Any]:
    groups: dict[str, list[DiagnosticObservation]] = {"overall": observations}
    for label in sorted({item.label for item in observations}):
        groups[f"label:{label}"] = [item for item in observations if item.label == label]
    for intensity in sorted({item.intensity for item in observations}):
        groups[f"intensity:{intensity:g}"] = [
            item for item in observations if item.intensity == intensity
        ]
    for category in sorted({item.category for item in observations}):
        groups[f"category:{category}"] = [
            item for item in observations if item.category == category
        ]
    return {name: _outcome_aggregate(items) for name, items in groups.items()}


def outcome_examples(
    observations: list[DiagnosticObservation],
    *,
    limit_per_outcome: int,
) -> dict[str, list[dict[str, Any]]]:
    if limit_per_outcome < 1:
        raise ValueError("limit_per_outcome은 1 이상이어야 합니다.")
    examples = {outcome: [] for outcome in OUTCOME_ORDER}
    for item in observations:
        outcome = classify_observation(item)
        if len(examples[outcome]) >= limit_per_outcome:
            continue
        examples[outcome].append(
            {
                "row_id": item.row_id,
                "seed_id": item.seed_id,
                "label": item.label,
                "category": item.category,
                "intensity": item.intensity,
                "initial_count": item.initial_count,
                "candidate_count": item.candidate_count,
                "best_initial_recall": item.best_initial_recall,
                "truncated": item.truncated,
            }
        )
    return examples


def _portable_input_path(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def load_priority_words(path: Path) -> tuple[str, ...]:
    words: list[str] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        word = raw_line.strip()
        if not word or word.startswith("#"):
            continue
        if word in seen:
            raise ValueError(f"priority lexicon 중복 단어: {word} ({line_number}행)")
        seen.add(word)
        words.append(word)
    if not words:
        raise ValueError("priority lexicon에 단어가 없습니다.")
    return tuple(words)


def main() -> int:
    args = parse_args()
    if args.word_limit < 1:
        raise ValueError("--word-limit은 1 이상이어야 합니다.")
    if args.max_candidates < 1 or args.max_options_per_span < 1:
        raise ValueError("후보 제한은 1 이상이어야 합니다.")
    if not 2 <= args.max_segments <= 4 or not 1 <= args.max_options_per_segment <= 4:
        raise ValueError("분할 제한이 잘못됐습니다.")
    if args.examples_per_outcome < 1:
        raise ValueError("--examples-per-outcome은 1 이상이어야 합니다.")

    try:
        from wordfreq import top_n_list
    except ImportError as exc:
        raise SystemExit(
            "wordfreq가 필요합니다: pip install -r "
            "experiments/guardrail/requirements-chosung.txt"
        ) from exc

    input_path = args.input.resolve()
    rows = load_benchmark(
        input_path,
        limit_seeds=args.limit_seeds,
        techniques={"chosung"},
    )
    variants = [row for row in rows if row.technique == "chosung"]
    wordfreq_words = top_n_list("ko", args.word_limit)
    priority_metadata = None
    if args.priority_lexicon is not None:
        priority_path = args.priority_lexicon.resolve()
        raw_priority_words = load_priority_words(priority_path)
        priority_words = (
            expand_korean_noun_particles(raw_priority_words)
            if args.expand_priority_particles
            else raw_priority_words
        )
        lexicon = ChosungLexicon.from_sources(
            [
                (args.priority_source, priority_words),
                ("wordfreq:ko", wordfreq_words),
            ]
        )
        priority_metadata = {
            "path": _portable_input_path(priority_path),
            "sha256": sha256_file(priority_path),
            "source": args.priority_source,
            "requested_words": len(raw_priority_words),
            "indexed_variants_before_deduplication": len(priority_words),
            "particle_expansion": args.expand_priority_particles,
        }
        lexicon_name = f"{args.priority_source}+wordfreq:ko"
    else:
        lexicon = ChosungLexicon.from_sources([("wordfreq:ko", wordfreq_words)])
        lexicon_name = "wordfreq:ko"
    observations = [
        observe_row(
            row.text,
            row.original,
            row.label,
            row.category,
            row.intensity,
            lexicon,
            min_initials=args.min_initials,
            max_options_per_span=args.max_options_per_span,
            max_candidates=args.max_candidates,
            allow_segmentation=args.allow_segmentation,
            max_segments=args.max_segments,
            max_options_per_segment=args.max_options_per_segment,
            row_id=row.row_id,
            seed_id=row.seed_id,
        )
        for row in variants
    ]
    result = {
        "status": "PROVISIONAL_DEV_ONLY",
        "validity_reasons": [
            "현재 공개 benchmark는 locked test로 재사용할 수 없음",
            "문맥 순위화·semantic fidelity·가드레일 판정을 측정하지 않음",
            "어휘 coverage 진단이며 방어 성능 주장을 지원하지 않음",
        ],
        "input": {
            "path": _portable_input_path(input_path),
            "sha256": sha256_file(input_path),
            "rows": len(variants),
            "independent_seeds": len({row.seed_id for row in variants}),
        },
        "candidate_generator": {
            "version": CHOSUNG_CANDIDATE_VERSION,
            "lexicon": lexicon_name,
            "wordfreq_version": version("wordfreq"),
            "word_limit": args.word_limit,
            "indexed_words": lexicon.word_count,
            "source_counts": dict(lexicon.source_counts),
            "priority_lexicon": priority_metadata,
            "min_initials": args.min_initials,
            "max_options_per_span": args.max_options_per_span,
            "max_candidates": args.max_candidates,
            "allow_segmentation": args.allow_segmentation,
            "max_segments": args.max_segments,
            "max_options_per_segment": args.max_options_per_segment,
        },
        "metrics": summarize(observations),
        "error_analysis": {
            "taxonomy_version": ERROR_TAXONOMY_VERSION,
            "definitions": OUTCOME_DEFINITIONS,
            "metrics": summarize_outcomes(observations),
            "examples": outcome_examples(
                observations,
                limit_per_outcome=args.examples_per_outcome,
            ),
        },
    }
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        output_path = args.output.resolve()
        if output_path.exists():
            raise SystemExit(f"출력 파일이 이미 있습니다: {output_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
