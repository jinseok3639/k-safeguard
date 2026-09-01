"""Build the static GitHub Pages artifact with the current package wheel."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = REPO_ROOT / "web"
PYODIDE_VERSION = "0.28.3"
BUILD_MARKER = ".k-safeguard-demo-build"


def wheel_metadata(wheel: Path) -> tuple[str, str]:
    with zipfile.ZipFile(wheel) as archive:
        metadata_names = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_names) != 1:
            raise ValueError("wheel METADATA 파일을 하나만 찾을 수 있어야 합니다.")
        metadata = archive.read(metadata_names[0]).decode("utf-8")
    fields: dict[str, str] = {}
    for line in metadata.splitlines():
        if ": " not in line:
            continue
        key, value = line.split(": ", 1)
        fields.setdefault(key, value)
    try:
        return fields["Name"], fields["Version"]
    except KeyError as exc:
        raise ValueError("wheel METADATA에 Name과 Version이 필요합니다.") from exc


def build_site(wheel: Path, output: Path, commit: str) -> dict[str, object]:
    wheel = wheel.resolve()
    output = output.resolve()
    if not wheel.is_file() or wheel.suffix != ".whl":
        raise ValueError("유효한 wheel 경로가 필요합니다.")
    if output == REPO_ROOT.resolve() or REPO_ROOT.resolve() not in output.parents:
        raise ValueError("output은 저장소 내부의 전용 디렉터리여야 합니다.")

    package_name, package_version = wheel_metadata(wheel)
    if output.exists() and not (output / BUILD_MARKER).is_file():
        raise ValueError("기존 output에 데모 빌드 표식이 없어 덮어쓰지 않습니다.")
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(WEB_ROOT, output, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    assets = output / "assets"
    assets.mkdir()
    deployed_wheel = assets / wheel.name
    shutil.copy2(wheel, deployed_wheel)

    manifest: dict[str, object] = {
        "schema_version": "web-demo-manifest-v1",
        "package_name": package_name,
        "package_version": package_version,
        "commit": commit,
        "pyodide_version": PYODIDE_VERSION,
        "wheel": f"./assets/{wheel.name}",
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
    }
    (assets / "demo-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / ".nojekyll").write_text("", encoding="utf-8")
    (output / BUILD_MARKER).write_text("generated; safe to replace\n", encoding="utf-8")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = build_site(args.wheel, args.output, args.commit)
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
