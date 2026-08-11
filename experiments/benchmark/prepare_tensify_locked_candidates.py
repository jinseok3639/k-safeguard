"""고정 외부 원천에서 된소리 locked-test 번역 후보를 결정론적으로 선택한다."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_REPO = "neuralchemy/Prompt-injection-dataset"
SOURCE_REVISION = "7d70432dfcf47a821612cbf9d34e9d9e3ad20e75"
SOURCE_FILES = {
    "train": "core/train-00000-of-00001.parquet",
    "validation": "core/validation-00000-of-00001.parquet",
    "test": "core/test-00000-of-00001.parquet",
}
SELECTION_SALT = "k-safeguard:tensify-locked:v1"
QUOTAS = {"A1_injection": 16, "A2_leaking": 12, "benign_hard_negative": 28}
BUCKET_QUOTAS = {
    "a1_original": 9,
    "a1_external": 7,
    "a2_original": 3,
    "a2_external": 9,
    "benign_original": 28,
}
A2_SOURCE_CATEGORIES = {"system_extraction", "prompt_extraction"}
_A1_LEXICON = re.compile(
    r"\b(ignore|instruction|safety|restriction|system|guardrail|context|filter|"
    r"unrestricted|previous|above|directive|ethical)\b",
    re.IGNORECASE,
)
_OUT_OF_SCOPE_PAYLOAD = re.compile(
    r"\b(bomb|explosive|malware|ransomware|meth|weapon|kill|murder)\b",
    re.IGNORECASE,
)
DEFAULT_EXCLUSION = REPO_ROOT / "SEED_CANDIDATES.csv"
DEFAULT_OUTPUT = REPO_ROOT / "build" / "tensify_locked_translation_template_v1.csv"
DEFAULT_MANIFEST = REPO_ROOT / "build" / "tensify_locked_source_selection_v1.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exclusion", type=Path, default=DEFAULT_EXCLUSION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    return parser.parse_args()


def canonical_source_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalized_source_text(text: str) -> str:
    return canonical_source_text(text).casefold()


def selection_key(group_id: str) -> str:
    return hashlib.sha256(f"{SELECTION_SALT}:{group_id}".encode("utf-8")).hexdigest()


def source_text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_excluded_groups(path: Path) -> set[str]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return {
            row["source_group_id"].strip()
            for row in csv.DictReader(stream)
            if row.get("source_dataset", "").strip() == SOURCE_REPO
            and row.get("source_group_id", "").strip()
        }


def selection_bucket(row: dict[str, Any], split: str) -> str | None:
    category = str(row["category"])
    source = str(row["source"])
    text = str(row["text"])
    if category == "direct_injection" and source == "original":
        return "a1_original"
    if (
        category == "direct_injection"
        and split == "test"
        and source != "original"
        and len(text) <= 300
        and _A1_LEXICON.search(text)
    ):
        return "a1_external"
    if category in A2_SOURCE_CATEGORIES:
        return "a2_original" if source == "original" else "a2_external"
    if category == "benign" and source == "original":
        return "benign_original"
    return None


def bucket_category(bucket: str) -> str:
    if bucket.startswith("a1_"):
        return "A1_injection"
    if bucket.startswith("a2_"):
        return "A2_leaking"
    return "benign_hard_negative"


def select_candidates(
    rows_by_split: dict[str, list[dict[str, Any]]],
    excluded_groups: set[str],
) -> list[dict[str, Any]]:
    pools: dict[str, list[dict[str, Any]]] = {bucket: [] for bucket in BUCKET_QUOTAS}
    seen_groups: set[str] = set()
    seen_texts: set[str] = set()
    for split in ("train", "validation", "test"):
        for source_row, row in enumerate(rows_by_split[split]):
            bucket = selection_bucket(row, split)
            if bucket is None:
                continue
            category = bucket_category(bucket)
            text = canonical_source_text(str(row["text"]))
            group_id = str(row["group_id"]).strip()
            if (
                not text
                or not text.isascii()
                or _OUT_OF_SCOPE_PAYLOAD.search(text)
                or not group_id
                or group_id in excluded_groups
                or group_id in seen_groups
            ):
                continue
            normalized = normalized_source_text(text)
            if normalized in seen_texts:
                continue
            seen_groups.add(group_id)
            seen_texts.add(normalized)
            pools[bucket].append(
                {
                    "label": "benign" if category == "benign_hard_negative" else "attack",
                    "category": category,
                    "subtype": str(row["category"]),
                    "source_text": text,
                    "source_dataset": SOURCE_REPO,
                    "source_revision": SOURCE_REVISION,
                    "source_split": split,
                    "source_row": source_row,
                    "source_group_id": group_id,
                    "source_text_sha256": source_text_sha256(text),
                    "selection_key": selection_key(group_id),
                }
            )

    selected_by_category: dict[str, list[dict[str, Any]]] = {
        category: [] for category in QUOTAS
    }
    for bucket, quota in BUCKET_QUOTAS.items():
        ranked = sorted(pools[bucket], key=lambda item: item["selection_key"])
        if len(ranked) < quota:
            raise ValueError(f"{bucket} 후보 부족: 필요 {quota}, 사용 가능 {len(ranked)}")
        selected_by_category[bucket_category(bucket)].extend(ranked[:quota])

    selected: list[dict[str, Any]] = []
    prefixes = {
        "A1_injection": "locked_a1",
        "A2_leaking": "locked_a2",
        "benign_hard_negative": "locked_bng",
    }
    for category, quota in QUOTAS.items():
        ranked = sorted(selected_by_category[category], key=lambda item: item["selection_key"])
        if len(ranked) != quota:
            raise AssertionError(f"{category} 선택 수 불일치")
        for rank, item in enumerate(ranked, start=1):
            selected.append(
                {
                    "sample_id": f"{prefixes[category]}_{rank:03d}",
                    **item,
                    "selection_rank": rank,
                    "korean_text": "",
                    "adaptation": "translation_pending",
                    "review_status": "team_review_needed",
                }
            )
    return selected


def load_source_rows() -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    try:
        import pyarrow.parquet as parquet
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise RuntimeError(
            "후보 준비에는 huggingface_hub와 pyarrow가 필요합니다."
        ) from exc

    rows: dict[str, list[dict[str, Any]]] = {}
    files: dict[str, str] = {}
    for split, filename in SOURCE_FILES.items():
        path = hf_hub_download(
            SOURCE_REPO,
            filename,
            repo_type="dataset",
            revision=SOURCE_REVISION,
        )
        files[split] = path
        rows[split] = parquet.read_table(path).to_pylist()
    return rows, files


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
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
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    args = parse_args()
    rows_by_split, source_files = load_source_rows()
    excluded = load_excluded_groups(args.exclusion.resolve())
    selected = select_candidates(rows_by_split, excluded)
    write_csv(args.output.resolve(), selected)
    manifest = {
        "schema_version": 1,
        "status": "SOURCE_SELECTION_FROZEN",
        "source": {
            "dataset": SOURCE_REPO,
            "revision": SOURCE_REVISION,
            "config": "core",
            "files": SOURCE_FILES,
            "local_files": source_files,
            "license": "Apache-2.0",
        },
        "selection": {
            "salt": SELECTION_SALT,
            "algorithm": "sha256(salt + ':' + source_group_id), ascending",
            "quotas": QUOTAS,
            "bucket_quotas": BUCKET_QUOTAS,
            "filters": [
                "A1: 9 unseen original rows plus 7 test rows from other sources",
                "A1 external rows: at most 300 chars and must contain a fixed "
                "injection lexicon term",
                "A2: 3 unseen original rows plus 9 clean rows from other sources",
                "A2 source categories: system_extraction or prompt_extraction",
                "benign: 28 original rows across frozen source splits",
                "ASCII clean source text only",
                "exclude fixed out-of-scope harmful-payload lexicon",
                "exclude source_group_id already present in SEED_CANDIDATES.csv",
                "deduplicate exact whitespace-normalized casefolded source text",
                "no model prediction used",
            ],
            "excluded_group_count": len(excluded),
        },
        "selected": [
            {key: value for key, value in row.items() if key not in {"source_text", "korean_text"}}
            for row in selected
        ],
        "counts": dict(Counter(row["category"] for row in selected)),
    }
    write_json(args.manifest.resolve(), manifest)
    print(json.dumps(manifest["counts"], ensure_ascii=False))
    print(f"output={args.output.resolve()}")
    print(f"manifest={args.manifest.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
