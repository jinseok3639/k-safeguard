"""된소리 locked-test 후보의 provenance·중복·검수 상태를 검증하고 봉인한다."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from experiments.benchmark.prepare_tensify_locked_candidates import QUOTAS
from experiments.benchmark.run_clean_baseline import git_metadata, sha256_file
from hf_repo.ko_obfuscator import tensify


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = (
    Path(__file__).resolve().parent / "data" / "tensify_locked_candidates_v1.csv"
)
DEFAULT_SELECTION = (
    Path(__file__).resolve().parent
    / "baselines"
    / "tensify_locked_source_selection_v1.json"
)
DEFAULT_SEAL = REPO_ROOT / "build" / "tensify_locked_seal_v2.json"
PROTOCOL_VERSION = "tensify-locked-v2"
RUNNER_PATH = Path(__file__).resolve().parent / "run_tensify_locked_evaluation.py"
REVIEWED_STATUS = "selected"
ALLOWED_SUBTYPES = {
    "A1_injection": {"direct_injection"},
    "A2_leaking": {"system_extraction", "prompt_extraction"},
    "benign_hard_negative": {"benign"},
}
REQUIRED_COLUMNS = {
    "sample_id",
    "label",
    "category",
    "subtype",
    "korean_text",
    "source_text",
    "source_dataset",
    "source_revision",
    "source_split",
    "source_row",
    "source_group_id",
    "source_text_sha256",
    "selection_key",
    "selection_rank",
    "adaptation",
    "review_status",
}


@dataclass(frozen=True)
class LockedCandidate:
    sample_id: str
    label: str
    category: str
    subtype: str
    text: str
    source_text: str
    source_dataset: str
    source_revision: str
    source_split: str
    source_row: int
    source_group_id: str
    source_text_sha256: str
    selection_key: str
    selection_rank: int
    adaptation: str
    review_status: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--seal-output", type=Path)
    parser.add_argument("--require-reviewed", action="store_true")
    return parser.parse_args()


def normalized_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def load_candidates(path: Path) -> list[LockedCandidate]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"locked CSV 필수 열 누락: {', '.join(sorted(missing))}")
        source_rows = list(reader)

    rows: list[LockedCandidate] = []
    ids: set[str] = set()
    texts: set[str] = set()
    for line_number, source in enumerate(source_rows, start=2):
        if source.get(None):
            raise ValueError(f"{line_number}행에 헤더보다 많은 CSV 값이 있습니다.")
        values = {key: source[key].strip() for key in REQUIRED_COLUMNS}
        empty = sorted(key for key, value in values.items() if not value)
        if empty:
            raise ValueError(f"{line_number}행 필수 값 누락: {', '.join(empty)}")
        sample_id = values["sample_id"]
        normalized = normalized_text(values["korean_text"])
        if sample_id in ids:
            raise ValueError(f"중복 sample_id: {sample_id}")
        if normalized in texts:
            raise ValueError(f"중복 korean_text: {sample_id}")
        ids.add(sample_id)
        texts.add(normalized)
        try:
            source_row = int(values["source_row"])
            selection_rank = int(values["selection_rank"])
        except ValueError as exc:
            raise ValueError(f"정수 provenance 값 오류: {sample_id}") from exc
        rows.append(
            LockedCandidate(
                sample_id=sample_id,
                label=values["label"],
                category=values["category"],
                subtype=values["subtype"],
                text=values["korean_text"],
                source_text=values["source_text"],
                source_dataset=values["source_dataset"],
                source_revision=values["source_revision"],
                source_split=values["source_split"],
                source_row=source_row,
                source_group_id=values["source_group_id"],
                source_text_sha256=values["source_text_sha256"],
                selection_key=values["selection_key"],
                selection_rank=selection_rank,
                adaptation=values["adaptation"],
                review_status=values["review_status"],
            )
        )
    if not rows:
        raise ValueError("locked 후보가 없습니다.")
    return rows


def load_reference_texts(repo_root: Path = REPO_ROOT) -> dict[str, set[str]]:
    references: dict[str, set[str]] = {}

    with (repo_root / "dev_note" / "SEED_CANDIDATES.csv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        references["SEED_CANDIDATES.csv"] = {
            normalized_text(row["korean_text"])
            for row in csv.DictReader(stream)
            if row["korean_text"].strip()
        }

    dev_path = (
        repo_root / "experiments" / "benchmark" / "data" / "tensify_benign_dev_v1.csv"
    )
    with dev_path.open(encoding="utf-8-sig", newline="") as stream:
        references["tensify_benign_dev_v1.csv"] = {
            normalized_text(row["text"])
            for row in csv.DictReader(stream)
            if row["text"].strip()
        }

    for name in ("attacks", "benign"):
        path = repo_root / "hf_repo" / "seeds" / f"{name}.jsonl"
        references[f"hf_repo/seeds/{name}.jsonl"] = {
            normalized_text(json.loads(line)["text"])
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
    return references


def validate_candidates(
    rows: list[LockedCandidate],
    selection: dict[str, Any],
    references: dict[str, set[str]],
) -> dict[str, Any]:
    if selection.get("status") != "SOURCE_SELECTION_FROZEN":
        raise ValueError("source selection이 frozen 상태가 아닙니다.")
    expected_by_id = {item["sample_id"]: item for item in selection["selected"]}
    if len(expected_by_id) != len(selection["selected"]):
        raise ValueError("source selection manifest에 중복 sample_id가 있습니다.")
    if {row.sample_id for row in rows} != set(expected_by_id):
        raise ValueError("후보 CSV와 source selection의 sample_id 집합이 다릅니다.")

    counts = Counter(row.category for row in rows)
    if dict(counts) != QUOTAS:
        raise ValueError(f"category quota 불일치: {dict(counts)}")
    overlaps: list[dict[str, str]] = []
    changed = 0
    for row in rows:
        expected = expected_by_id[row.sample_id]
        if (
            row.source_dataset != selection["source"]["dataset"]
            or row.source_revision != selection["source"]["revision"]
        ):
            raise ValueError(f"source dataset/revision 불일치: {row.sample_id}")
        if row.subtype not in ALLOWED_SUBTYPES.get(row.category, set()):
            raise ValueError(f"category/subtype 불일치: {row.sample_id}")
        if row.adaptation != "ko_translation_v1":
            raise ValueError(f"adaptation 불일치: {row.sample_id}")
        actual_source_sha = hashlib.sha256(row.source_text.encode("utf-8")).hexdigest()
        if actual_source_sha != row.source_text_sha256:
            raise ValueError(f"source text SHA-256 불일치: {row.sample_id}")
        comparable = {
            "label": row.label,
            "category": row.category,
            "source_split": row.source_split,
            "source_row": row.source_row,
            "source_group_id": row.source_group_id,
            "source_text_sha256": row.source_text_sha256,
            "selection_key": row.selection_key,
            "selection_rank": row.selection_rank,
        }
        for key, value in comparable.items():
            if expected[key] != value:
                raise ValueError(f"source selection 불일치: {row.sample_id}.{key}")
        normalized = normalized_text(row.text)
        for source_name, source_texts in references.items():
            if normalized in source_texts:
                overlaps.append({"sample_id": row.sample_id, "source": source_name})
        changed += tensify(row.text, intensity=1.0) != row.text
    if overlaps:
        raise ValueError(f"개발 데이터와 exact text 중복: {overlaps}")
    if changed != len(rows):
        raise ValueError(f"tensify가 적용되지 않는 후보가 있습니다: {changed}/{len(rows)}")

    review_counts = Counter(row.review_status for row in rows)
    reviewed = review_counts == {REVIEWED_STATUS: len(rows)}
    return {
        "status": "READY_TO_SEAL" if reviewed else "REVIEW_PENDING",
        "rows": len(rows),
        "counts": dict(counts),
        "review_statuses": dict(review_counts),
        "tensify_changed": changed,
        "exact_overlap_count": 0,
        "source_selection_status": selection["status"],
    }


def build_seal(
    input_path: Path,
    selection_path: Path,
    rows: list[LockedCandidate],
    summary: dict[str, Any],
) -> dict[str, Any]:
    if summary["status"] != "READY_TO_SEAL":
        raise ValueError("모든 행이 selected 검수 상태여야 봉인할 수 있습니다.")
    ids_payload = "\n".join(sorted(row.sample_id for row in rows)).encode("utf-8")
    return {
        "schema_version": 1,
        "protocol_version": PROTOCOL_VERSION,
        "status": "SEALED_NOT_EVALUATED",
        "sealed_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "path": str(input_path.resolve().relative_to(REPO_ROOT)).replace("\\", "/"),
            "sha256": sha256_file(input_path),
            "rows": len(rows),
            "sample_ids_sha256": hashlib.sha256(ids_payload).hexdigest(),
        },
        "source_selection": {
            "path": str(selection_path.resolve().relative_to(REPO_ROOT)).replace("\\", "/"),
            "sha256": sha256_file(selection_path),
        },
        "implementation": {
            "git": git_metadata(),
            "runner_sha256": sha256_file(RUNNER_PATH),
        },
        "validation": summary,
        "policy": {
            "candidate": "ratio_0.10",
            "min_tense_syllables": 1,
            "min_tense_ratio": 0.10,
            "max_candidates": 9,
            "max_views": 10,
        },
        "rules": {
            "run_once_after_sealing": True,
            "no_policy_change_after_result": True,
            "translation_fixes_allowed_before_sealing_only": True,
            "source_rejection_requires_new_preregistered_dataset_version": True,
        },
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    input_path = args.input.resolve()
    selection_path = args.selection.resolve()
    rows = load_candidates(input_path)
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    summary = validate_candidates(rows, selection, load_reference_texts())
    if args.seal_output is not None:
        if summary["status"] != "READY_TO_SEAL":
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            print("검수 전에는 seal을 생성하지 않습니다.")
            return 2
        seal = build_seal(input_path, selection_path, rows, summary)
        if seal["implementation"]["git"]["dirty"]:
            print("dirty worktree에서는 seal을 생성하지 않습니다.")
            return 2
        write_json(args.seal_output.resolve(), seal)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.require_reviewed and summary["status"] != "READY_TO_SEAL":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
