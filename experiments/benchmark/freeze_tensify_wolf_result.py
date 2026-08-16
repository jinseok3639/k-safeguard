"""Wolf Defender 교차 모델 결과와 실행 seal을 경로 독립 baseline으로 고정한다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from experiments.benchmark.run_clean_baseline import sha256_file
from experiments.benchmark.run_tensify_wolf_cross_model import PROTOCOL_VERSION, REPO_ROOT


BASELINE_DIR = Path(__file__).resolve().parent / "baselines"
DEFAULT_OUTPUT = BASELINE_DIR / "tensify_wolf_cross_model_v1.json"
DEFAULT_SEAL_OUTPUT = BASELINE_DIR / "tensify_wolf_cross_model_seal_v1.json"
ARTIFACTS = (
    "summary.json",
    "manifest.json",
    "predictions.jsonl",
    "subgroups.csv",
    "errors.jsonl",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seal-output", type=Path, default=DEFAULT_SEAL_OUTPUT)
    return parser.parse_args()


def portable_path(value: str) -> str:
    path = Path(value).resolve()
    try:
        return str(path.relative_to(REPO_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return path.name


def freeze_result(result_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    result_dir = result_dir.resolve()
    missing = [name for name in ARTIFACTS if not (result_dir / name).exists()]
    if missing:
        raise ValueError(f"cross-model result artifact 누락: {', '.join(missing)}")
    summary = json.loads((result_dir / "summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((result_dir / "manifest.json").read_text(encoding="utf-8"))
    if summary.get("status") != "CROSS_MODEL_REPLICATION":
        raise ValueError("Wolf cross-model summary만 고정할 수 있습니다.")
    if summary.get("evidence_status") not in {
        "VALID_OOD_REPLICATION",
        "LIMITED_BASELINE_COVERAGE",
        "INVALID_EXECUTION",
    }:
        raise ValueError("알 수 없는 evidence status입니다.")
    if manifest.get("protocol_version") != PROTOCOL_VERSION:
        raise ValueError("Wolf cross-model protocol 결과가 아닙니다.")
    if manifest.get("run_id") != result_dir.name:
        raise ValueError("result directory와 manifest run_id가 다릅니다.")
    execution_seal = Path(manifest["seal"]["path"])
    if not execution_seal.exists():
        raise ValueError("manifest가 가리키는 실행 seal이 없습니다.")
    seal = json.loads(execution_seal.read_text(encoding="utf-8"))
    if sha256_file(execution_seal) != manifest["seal"]["sha256"]:
        raise ValueError("manifest 이후 실행 seal이 변경되었습니다.")
    model = dict(manifest["model"])
    model.pop("model_path", None)
    frozen = {
        "schema_version": 1,
        "status": summary["status"],
        "run_id": manifest["run_id"],
        "created_at": manifest["created_at"],
        "provenance": {
            "protocol_version": manifest["protocol_version"],
            "spec_version": manifest["spec_version"],
            "git": manifest["git"],
            "dataset": {
                "path": portable_path(manifest["dataset"]["path"]),
                "sha256": manifest["dataset"]["sha256"],
            },
            "source_selection": {
                "path": portable_path(manifest["selection"]["path"]),
                "sha256": manifest["selection"]["sha256"],
            },
            "seal": {
                "execution_path": portable_path(manifest["seal"]["path"]),
                "archived_path": portable_path(str(DEFAULT_SEAL_OUTPUT)),
                "sha256": manifest["seal"]["sha256"],
            },
            "candidate_generator": manifest["candidate_generator"],
            "model": model,
            "model_lock": {
                "sha256": manifest["model_lock"]["sha256"],
                "resolved_revision": manifest["model_lock"]["resolved_revision"],
            },
            "runtime": manifest["runtime"],
        },
        "artifact_sha256": {name: sha256_file(result_dir / name) for name in ARTIFACTS},
        "result": summary,
    }
    return frozen, seal


def main() -> int:
    args = parse_args()
    frozen, seal = freeze_result(args.result_dir)
    output = args.output.resolve()
    seal_output = args.seal_output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    seal_output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    seal_output.write_text(json.dumps(seal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"evidence_status={frozen['result']['evidence_status']}")
    print(f"output={output}")
    print(f"seal_output={seal_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
