"""로컬 locked-test 원시 결과를 경로 독립적인 추적 baseline으로 고정한다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from experiments.benchmark.run_clean_baseline import sha256_file


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = (
    Path(__file__).resolve().parent / "baselines" / "tensify_locked_v2.json"
)
ARCHIVED_SEAL = (
    Path(__file__).resolve().parent
    / "baselines"
    / "tensify_locked_seal_v2.json"
)
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
    return parser.parse_args()


def portable_path(value: str, repo_root: Path = REPO_ROOT) -> str:
    path = Path(value).resolve()
    try:
        return str(path.relative_to(repo_root.resolve())).replace("\\", "/")
    except ValueError:
        return path.name


def freeze_result(result_dir: Path) -> dict[str, Any]:
    result_dir = result_dir.resolve()
    missing = [name for name in ARTIFACTS if not (result_dir / name).exists()]
    if missing:
        raise ValueError(f"locked result artifact 누락: {', '.join(missing)}")

    summary = json.loads((result_dir / "summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((result_dir / "manifest.json").read_text(encoding="utf-8"))
    if summary.get("status") != "LOCKED_TEST_PRIMARY":
        raise ValueError("primary locked-test summary만 고정할 수 있습니다.")
    if manifest.get("run_id") != result_dir.name:
        raise ValueError("result directory와 manifest run_id가 다릅니다.")
    if summary.get("decision", {}).get("status") not in {
        "RECOMMEND_RATIO_0.10_PRESET",
        "DO_NOT_PROMOTE",
        "INVALID_OR_INCONCLUSIVE",
    }:
        raise ValueError("locked decision status가 없거나 알 수 없습니다.")

    model = dict(manifest["model"])
    model.pop("model_path", None)
    if not ARCHIVED_SEAL.exists():
        raise ValueError("추적 가능한 archived seal이 없습니다.")
    execution_seal = Path(manifest["seal"]["path"])
    if not execution_seal.exists():
        raise ValueError("manifest가 가리키는 실행 seal이 없습니다.")
    archived_seal = json.loads(ARCHIVED_SEAL.read_text(encoding="utf-8"))
    executed_seal = json.loads(execution_seal.read_text(encoding="utf-8"))
    if archived_seal != executed_seal:
        raise ValueError("실행 seal과 archived seal의 JSON 내용이 다릅니다.")
    return {
        "schema_version": 1,
        "status": summary["status"],
        "run_id": manifest["run_id"],
        "created_at": manifest["created_at"],
        "provenance": {
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
                "archived_path": portable_path(str(ARCHIVED_SEAL)),
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
        "artifact_sha256": {
            name: sha256_file(result_dir / name) for name in ARTIFACTS
        },
        "result": summary,
    }


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    frozen = freeze_result(args.result_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(frozen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"decision={frozen['result']['decision']['status']}")
    print(f"output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
