from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = SCRIPT_DIR / "models.json"
DEFAULT_MODEL_HOME = Path(r"D:\local llm\guardrails")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="고정 revision의 가드레일 모델을 내려받습니다.")
    parser.add_argument(
        "--model-home",
        type=Path,
        default=Path(os.environ.get("K_SAFEGUARD_MODEL_HOME", DEFAULT_MODEL_HOME)),
    )
    parser.add_argument(
        "--model",
        action="append",
        dest="model_keys",
        help="models.json의 key. 여러 번 지정할 수 있습니다.",
    )
    parser.add_argument(
        "--include-optional",
        action="store_true",
        help="약관 동의가 필요한 선택 모델도 다운로드합니다.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def select_models(manifest: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    models = manifest["models"]
    by_key = {model["key"]: model for model in models}
    if args.model_keys:
        unknown = sorted(set(args.model_keys) - set(by_key))
        if unknown:
            raise SystemExit(f"알 수 없는 model key: {', '.join(unknown)}")
        return [by_key[key] for key in args.model_keys]
    return [
        model
        for model in models
        if model["download_default"] or (args.include_optional and model["tier"] == "optional")
    ]


def directory_size(path: Path) -> int:
    return sum(file.stat().st_size for file in path.rglob("*") if file.is_file())


def main() -> int:
    args = parse_args()
    manifest = load_manifest()
    selected = select_models(manifest, args)
    model_home = args.model_home.resolve()
    model_dir = model_home / "models"
    hf_home = model_home / "hf-home"
    model_dir.mkdir(parents=True, exist_ok=True)
    hf_home.mkdir(parents=True, exist_ok=True)

    os.environ["HF_HOME"] = str(hf_home)
    os.environ["HF_HUB_CACHE"] = str(hf_home / "hub")
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

    from huggingface_hub import HfApi, snapshot_download
    from huggingface_hub.errors import GatedRepoError, HfHubHTTPError

    expected_bytes = int(sum(model["download_size_gb"] for model in selected) * 1024**3)
    free_bytes = shutil.disk_usage(model_home).free
    print(f"model_home={model_home}")
    print(f"selected={', '.join(model['key'] for model in selected)}")
    print(f"expected_download_gb={expected_bytes / 1024**3:.2f}")
    print(f"free_space_gb={free_bytes / 1024**3:.2f}")
    if free_bytes < expected_bytes + 5 * 1024**3:
        raise SystemExit("모델 다운로드 후 최소 5 GiB 여유 공간을 확보해야 합니다.")
    if args.dry_run:
        return 0

    api = HfApi()
    lock_path = model_home / "models.lock.json"
    if lock_path.exists():
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        lock.setdefault("models", {})
    else:
        lock = {"schema_version": 1, "models": {}}
    lock["generated_at"] = datetime.now(timezone.utc).isoformat()
    lock["model_home"] = str(model_home)
    failures: list[str] = []

    for model in selected:
        key = model["key"]
        destination = model_dir / key
        print(f"\n[{key}] {model['model_id']}@{model['revision']}")
        try:
            snapshot_download(
                repo_id=model["model_id"],
                revision=model["revision"],
                local_dir=destination,
                token=True if model["gated"] else None,
                max_workers=4,
            )
            info = api.model_info(
                repo_id=model["model_id"],
                revision=model["revision"],
                token=True if model["gated"] else None,
            )
            actual_bytes = directory_size(destination)
            lock["models"][key] = {
                "model_id": model["model_id"],
                "requested_revision": model["revision"],
                "resolved_revision": info.sha,
                "path": str(destination.resolve()),
                "size_bytes": actual_bytes,
                "license": model["license"],
            }
            print(f"downloaded_gb={actual_bytes / 1024**3:.2f}")
        except GatedRepoError:
            failures.append(key)
            print(
                "SKIP: 모델 약관 승인 또는 Hugging Face 로그인이 필요합니다. "
                f"{model['source']}",
                file=sys.stderr,
            )
        except HfHubHTTPError as exc:
            failures.append(key)
            print(f"FAIL: {exc}", file=sys.stderr)

    lock_path.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nlock_file={lock_path}")
    if failures:
        print(f"failed_or_skipped={', '.join(failures)}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
