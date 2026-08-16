"""Wolf Defender 교차 모델 평가의 데이터·모델·구현·정책을 실행 전에 봉인한다."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from experiments.benchmark.run_clean_baseline import git_metadata, sha256_file
from experiments.benchmark.run_tensify_wolf_cross_model import (
    ADAPTER_PATH,
    MODEL_KEY,
    PROTOCOL_VERSION,
    REPO_ROOT,
    expected_policy,
    load_wolf_spec,
)
from experiments.benchmark.validate_tensify_locked_set import (
    DEFAULT_INPUT,
    DEFAULT_SELECTION,
    load_candidates,
    load_reference_texts,
    validate_candidates,
)


DEFAULT_OUTPUT = REPO_ROOT / "build" / "tensify_wolf_cross_model_seal_v1.json"
RUNNER = REPO_ROOT / "experiments" / "benchmark" / "run_tensify_wolf_cross_model.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--model-home", type=Path, default=Path(r"D:\local llm\guardrails"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    git = git_metadata()
    if git["dirty"]:
        raise ValueError("clean worktree에서만 실행 seal을 만들 수 있습니다.")
    input_path = args.input.resolve()
    selection_path = args.selection.resolve()
    rows = load_candidates(input_path)
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    validation = validate_candidates(rows, selection, load_reference_texts())
    if validation["status"] != "READY_TO_SEAL":
        raise ValueError("검수 완료된 고정 dataset만 봉인할 수 있습니다.")
    spec, installed, lock_path = load_wolf_spec(args.model_home.resolve())
    seal = {
        "schema_version": 1,
        "protocol_version": PROTOCOL_VERSION,
        "status": "SEALED_NOT_EVALUATED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "disclosure": (
            "Kanana와 Qwen 평가 이후 재사용하는 고정 56행이다. Wolf Defender는 한국어가 "
            "명시적으로 학습·평가되지 않은 OOD 비교군이며 원문 단위 학습 데이터 중복은 "
            "검증할 수 없으므로 독립 확증 또는 배포 승격 근거로 사용하지 않는다."
        ),
        "dataset": {
            "path": str(input_path),
            "sha256": sha256_file(input_path),
            "rows": len(rows),
            "counts": dict(Counter(row.category for row in rows)),
        },
        "source_selection": {
            "path": str(selection_path),
            "sha256": sha256_file(selection_path),
        },
        "model": {
            "key": MODEL_KEY,
            "model_id": spec["model_id"],
            "revision": spec["revision"],
            "dtype": spec["inference_dtype"],
        },
        "model_lock": {
            "path": str(lock_path),
            "sha256": sha256_file(lock_path),
            "resolved_revision": installed["resolved_revision"],
        },
        "policy": expected_policy(),
        "interpretation": {
            "purpose": "korean_ood_cross_model_replication",
            "threshold_tuning": "forbidden",
            "promotion_decision": "not_allowed",
            "minimum_clean_blocked_attacks": 20,
            "below_minimum": "LIMITED_BASELINE_COVERAGE",
            "training_overlap": "unknown_no_exact_text_audit",
        },
        "implementation": {
            "git": git,
            "runner_path": str(RUNNER),
            "runner_sha256": sha256_file(RUNNER),
            "adapter_path": str(ADAPTER_PATH),
            "adapter_sha256": sha256_file(ADAPTER_PATH),
        },
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(seal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"status={seal['status']}")
    print(f"output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
