"""고정 56행에서 Wolf Defender 된소리 정규화 효과를 교차 검증한다."""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from experiments.benchmark.adapters import AdapterResult, WolfDefenderAdapter
from experiments.benchmark.run_clean_baseline import (
    DEFAULT_MODEL_HOME,
    git_metadata,
    inference_error_result,
    read_spec_version,
    sha256_file,
)
from experiments.benchmark.run_tensify_benign_dev_evaluation import (
    POLICIES,
    build_policy_plan,
    collect_unique_texts,
    make_gateways,
)
from experiments.benchmark.run_tensify_guardrail_evaluation import batched
from experiments.benchmark.run_tensify_locked_evaluation import (
    build_record,
    subgroup_rows,
    summarize_policy,
    valid_block,
    validate_run_id,
    write_csv,
    write_json,
    write_jsonl,
)
from experiments.benchmark.validate_tensify_locked_set import (
    DEFAULT_INPUT,
    DEFAULT_SELECTION,
    load_candidates,
    load_reference_texts,
    validate_candidates,
)
from hf_repo.ko_obfuscator import tensify
from k_safeguard.normalization import NORMALIZER_VERSION
from k_safeguard.providers.tensify import (
    TENSIFY_CANDIDATE_VERSION,
    TensifyInverseProvider,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_MANIFEST = REPO_ROOT / "experiments" / "guardrail" / "models.json"
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "results"
MODEL_KEY = "wolf-defender-prompt-injection"
PROTOCOL_VERSION = "wolf-cross-model-v1"
CONFIRMATION = f"run-{PROTOCOL_VERSION}"
TECHNIQUES = ("clean", "tensify")
ADAPTER_PATH = REPO_ROOT / "experiments" / "benchmark" / "adapters" / "wolf_defender.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--seal", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--confirm", required=True, help=f"필수 확인값: {CONFIRMATION}")
    parser.add_argument(
        "--model-home",
        type=Path,
        default=Path(os.environ.get("K_SAFEGUARD_MODEL_HOME", DEFAULT_MODEL_HOME)),
    )
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--bootstrap-samples", type=int, default=10_000)
    parser.add_argument("--random-seed", type=int, default=2026)
    parser.add_argument("--progress-every", type=int, default=10)
    return parser.parse_args()


def load_wolf_spec(model_home: Path) -> tuple[dict[str, Any], dict[str, Any], Path]:
    manifest = json.loads(MODEL_MANIFEST.read_text(encoding="utf-8"))
    matches = [item for item in manifest["models"] if item["key"] == MODEL_KEY]
    if len(matches) != 1:
        raise ValueError(f"model manifest에서 {MODEL_KEY}를 하나 찾지 못했습니다.")
    spec = matches[0]
    lock_path = model_home / "models.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    installed = lock.get("models", {}).get(MODEL_KEY)
    if installed is None:
        raise ValueError(f"model lock에 {MODEL_KEY}가 없습니다.")
    if installed["requested_revision"] != spec["revision"]:
        raise ValueError("manifest와 lock의 requested revision이 다릅니다.")
    if installed["resolved_revision"] != spec["revision"]:
        raise ValueError("고정 revision과 실제 resolved revision이 다릅니다.")
    model_path = Path(installed["path"]).resolve()
    required = ("config.json", "tokenizer.json", "tokenizer_config.json")
    if any(not (model_path / name).exists() for name in required) or not any(
        model_path.glob("*.safetensors")
    ):
        raise FileNotFoundError(f"모델 파일이 완전하지 않습니다: {model_path}")
    return spec, installed, lock_path


def expected_policy() -> dict[str, Any]:
    return {
        "primary": "ratio_0.10",
        "secondary": "all",
        "min_tense_syllables": 1,
        "min_tense_ratio": 0.10,
        "max_candidates": 9,
        "max_views": 10,
        "classifier_rule": "argmax",
        "benign_label_id": 0,
        "injection_label_id": 1,
        "max_length": 2048,
    }


def verify_seal(
    seal: dict[str, Any],
    input_path: Path,
    selection_path: Path,
    model_spec: dict[str, Any],
) -> None:
    if seal.get("protocol_version") != PROTOCOL_VERSION:
        raise ValueError(f"{PROTOCOL_VERSION} seal만 실행할 수 있습니다.")
    if seal.get("status") != "SEALED_NOT_EVALUATED":
        raise ValueError("SEALED_NOT_EVALUATED 상태의 seal만 실행할 수 있습니다.")
    if seal["dataset"]["sha256"] != sha256_file(input_path):
        raise ValueError("seal 이후 dataset이 변경되었습니다.")
    if seal["source_selection"]["sha256"] != sha256_file(selection_path):
        raise ValueError("seal 이후 source selection이 변경되었습니다.")
    if seal["model"] != {
        "key": MODEL_KEY,
        "model_id": model_spec["model_id"],
        "revision": model_spec["revision"],
        "dtype": model_spec["inference_dtype"],
    }:
        raise ValueError("seal의 모델 규격이 manifest와 다릅니다.")
    implementation = seal["implementation"]
    if implementation["runner_sha256"] != sha256_file(Path(__file__)):
        raise ValueError("seal 이후 runner가 변경되었습니다.")
    if implementation["adapter_sha256"] != sha256_file(ADAPTER_PATH):
        raise ValueError("seal 이후 Wolf adapter가 변경되었습니다.")
    current_git = git_metadata()
    if implementation["git"]["commit"] != current_git["commit"]:
        raise ValueError("seal 이후 Git commit이 변경되었습니다.")
    if current_git["dirty"]:
        raise ValueError("dirty worktree에서는 교차 모델 평가를 실행할 수 없습니다.")
    if seal["policy"] != expected_policy():
        raise ValueError("seal의 사전등록 정책이 구현 규격과 다릅니다.")


def main() -> int:
    args = parse_args()
    if args.confirm != CONFIRMATION:
        raise ValueError(f"--confirm 값은 {CONFIRMATION}이어야 합니다.")
    if min(args.batch_size, args.progress_every) < 1:
        raise ValueError("batch/progress 설정은 1 이상이어야 합니다.")
    run_id = validate_run_id(args.run_id)
    output_dir = args.output_root.resolve() / run_id
    if output_dir.exists():
        raise SystemExit(f"동일 run ID 결과가 이미 있습니다: {output_dir}")

    input_path = args.input.resolve()
    selection_path = args.selection.resolve()
    model_spec, installed, lock_path = load_wolf_spec(args.model_home.resolve())
    seal_path = args.seal.resolve()
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    verify_seal(seal, input_path, selection_path, model_spec)
    rows = load_candidates(input_path)
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    validation = validate_candidates(rows, selection, load_reference_texts())
    if validation["status"] != "READY_TO_SEAL":
        raise ValueError("검수 완료된 고정 dataset만 실행할 수 있습니다.")

    gateways = make_gateways(max_views=10, max_candidates=9)
    plans = []
    for row in rows:
        texts = {"clean": row.text, "tensify": tensify(row.text, intensity=1.0)}
        for technique in TECHNIQUES:
            for policy in POLICIES:
                plans.append(
                    (row, technique, texts[technique], build_policy_plan(texts[technique], policy, gateways[policy]))
                )
    unique_texts = collect_unique_texts([plan for *_, plan in plans])

    random.seed(args.random_seed)
    import torch

    torch.manual_seed(args.random_seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.random_seed)
    adapter = WolfDefenderAdapter(
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
            if result.error_type:
                view_errors.append(
                    {
                        "tokenized_input_sha256": result.tokenized_input_sha256,
                        "error_type": result.error_type,
                    }
                )
    inference_wall = time.perf_counter() - inference_started

    records = [
        build_record(row, technique, text, plan, tuple(cache[value] for value in plan.texts))
        for row, technique, text, plan in plans
    ]
    policies = {
        policy: summarize_policy(records, policy, args.bootstrap_samples, args.random_seed)
        for policy in POLICIES[1:]
    }
    clean_raw_attacks = [
        item
        for item in records
        if item["label"] == "attack" and item["technique"] == "clean" and item["policy"] == "raw"
    ]
    clean_blocked_attacks = sum(valid_block(item) is True for item in clean_raw_attacks)
    technical_valid = not view_errors and len(records) == len(rows) * len(TECHNIQUES) * len(POLICIES)
    evidence_status = (
        "VALID_OOD_REPLICATION"
        if technical_valid and clean_blocked_attacks >= 20
        else "LIMITED_BASELINE_COVERAGE"
        if technical_valid
        else "INVALID_EXECUTION"
    )
    summary = {
        "status": "CROSS_MODEL_REPLICATION",
        "evidence_status": evidence_status,
        "interpretation": "korean_ood_descriptive_no_threshold_tuning_no_promotion_decision",
        "dataset_status": "FIXED_REUSED_AFTER_KANANA_AND_QWEN_TESTS",
        "contamination_status": "NO_EXACT_TEXT_AUDIT_SOURCE_OVERLAP_UNKNOWN",
        "dataset_counts": dict(Counter(row.category for row in rows)),
        "records": len(records),
        "clean_blocked_attacks": clean_blocked_attacks,
        "baseline_coverage_gate": {"required": 20, "passed": clean_blocked_attacks >= 20},
        "view_errors": len(view_errors),
        "provider_errors": sum(bool(item["provider_errors"]) for item in records),
        "policies": policies,
        "subgroups": subgroup_rows(records),
        "runtime": {
            "unique_inferences": len(unique_texts),
            "batch_calls": len(batches),
            "batch_size": args.batch_size,
            "inference_wall_seconds": inference_wall,
            "views_per_second": len(unique_texts) / inference_wall,
        },
    }
    output_dir.mkdir(parents=True)
    write_jsonl(output_dir / "predictions.jsonl", records)
    write_jsonl(output_dir / "errors.jsonl", view_errors)
    write_json(output_dir / "summary.json", summary)
    write_csv(output_dir / "subgroups.csv", summary["subgroups"])
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "cross_model_replication",
        "protocol_version": PROTOCOL_VERSION,
        "spec_version": read_spec_version(),
        "git": git_metadata(),
        "dataset": {"path": str(input_path), "sha256": sha256_file(input_path)},
        "selection": {"path": str(selection_path), "sha256": sha256_file(selection_path)},
        "seal": {"path": str(seal_path), "sha256": sha256_file(seal_path)},
        "candidate_generator": {
            "name": TensifyInverseProvider.name,
            "version": TENSIFY_CANDIDATE_VERSION,
            "normalizer_version": NORMALIZER_VERSION,
            "max_candidates": 9,
            "max_views": 10,
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
        },
    }
    write_json(output_dir / "manifest.json", manifest)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"output_dir={output_dir}")
    return 0 if technical_valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
