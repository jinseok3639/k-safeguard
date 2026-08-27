"""배포 전에 소스 버전과 wheel/sdist 경계를 검증한다.

외부 패키지 없이 Python 3.10 이상에서 실행할 수 있도록 표준 라이브러리만 사용한다.
"""

from __future__ import annotations

import argparse
import ast
from email.parser import Parser
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
INIT_PATH = PROJECT_ROOT / "src" / "k_safeguard" / "__init__.py"

REQUIRED_PACKAGE_FILES = {
    "k_safeguard/__init__.py",
    "k_safeguard/chosung.py",
    "k_safeguard/gateway.py",
    "k_safeguard/normalization.py",
    "k_safeguard/providers/__init__.py",
    "k_safeguard/providers/chosung.py",
    "k_safeguard/providers/wordfreq.py",
    "k_safeguard/py.typed",
}
FORBIDDEN_TOP_LEVEL = {
    "dev_note",
    "experiments",
    "hf_repo",
    "reports",
    "tests",
    "tools",
    "참조용",
}
FORBIDDEN_SUFFIXES = {
    ".bin",
    ".ckpt",
    ".csv",
    ".gguf",
    ".ipynb",
    ".jsonl",
    ".onnx",
    ".parquet",
    ".pt",
    ".pth",
    ".safetensors",
}


class VerificationError(RuntimeError):
    """릴리스 검증 실패."""


def _project_table_value(path: Path, key: str) -> str:
    """현재 프로젝트의 단순 scalar 값을 Python 3.10에서도 읽는다."""

    in_project = False
    assignment = re.compile(
        rf"^{re.escape(key)}\s*=\s*(['\"])(?P<value>.+?)\1\s*(?:#.*)?$"
    )
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            in_project = line == "[project]"
            continue
        if in_project:
            match = assignment.match(line)
            if match:
                return match.group("value")
    raise VerificationError(f"{path}의 [project]에서 {key!r} 값을 찾지 못했습니다.")


def _module_version(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return node.value.value
    raise VerificationError(f"{path}에서 문자열 __version__을 찾지 못했습니다.")


def verify_source_versions(project_root: Path = PROJECT_ROOT) -> tuple[str, str]:
    pyproject = project_root / "pyproject.toml"
    init_file = project_root / "src" / "k_safeguard" / "__init__.py"
    name = _project_table_value(pyproject, "name")
    project_version = _project_table_value(pyproject, "version")
    module_version = _module_version(init_file)
    if project_version != module_version:
        raise VerificationError(
            "배포 버전 불일치: "
            f"pyproject.toml={project_version!r}, k_safeguard.__version__={module_version!r}"
        )
    return name, project_version


def _normalized_distribution(name: str) -> str:
    return re.sub(r"[-_.]+", "_", name).lower()


def _forbidden_wheel_members(members: list[str]) -> list[str]:
    forbidden: list[str] = []
    for member in members:
        path = PurePosixPath(member)
        if path.parts and path.parts[0] in FORBIDDEN_TOP_LEVEL:
            forbidden.append(member)
        elif path.suffix.lower() in FORBIDDEN_SUFFIXES:
            forbidden.append(member)
    return forbidden


def verify_wheel(path: Path, project_name: str, version: str) -> None:
    distribution = _normalized_distribution(project_name)
    expected_filename = f"{distribution}-{version}-py3-none-any.whl"
    if path.name != expected_filename:
        raise VerificationError(
            f"wheel 파일명이 예상과 다릅니다: {path.name!r} != {expected_filename!r}"
        )

    dist_info = f"{distribution}-{version}.dist-info"
    metadata_name = f"{dist_info}/METADATA"
    wheel_name = f"{dist_info}/WHEEL"
    with zipfile.ZipFile(path) as archive:
        members = archive.namelist()
        missing = sorted(REQUIRED_PACKAGE_FILES.difference(members))
        if missing:
            raise VerificationError(f"wheel에 필수 파일이 없습니다: {', '.join(missing)}")
        forbidden = _forbidden_wheel_members(members)
        if forbidden:
            raise VerificationError(
                "wheel에 런타임 경계 밖 파일이 포함됐습니다: " + ", ".join(forbidden)
            )
        for required in (metadata_name, wheel_name):
            if required not in members:
                raise VerificationError(f"wheel에 {required}가 없습니다.")

        metadata = Parser().parsestr(archive.read(metadata_name).decode("utf-8"))
        wheel_metadata = Parser().parsestr(archive.read(wheel_name).decode("utf-8"))

    expected_metadata = {
        "Name": project_name,
        "Version": version,
        "Requires-Python": ">=3.10",
    }
    for key, expected in expected_metadata.items():
        actual = metadata.get(key)
        if actual != expected:
            raise VerificationError(f"METADATA {key}: {actual!r} != {expected!r}")

    unconditional = [
        requirement
        for requirement in metadata.get_all("Requires-Dist", [])
        if "extra ==" not in requirement
    ]
    if unconditional:
        raise VerificationError(
            "기본 설치에 런타임 의존성이 생겼습니다: " + ", ".join(unconditional)
        )
    if wheel_metadata.get("Root-Is-Purelib") != "true":
        raise VerificationError("wheel이 pure Python 패키지로 표시되지 않았습니다.")
    if wheel_metadata.get_all("Tag", []) != ["py3-none-any"]:
        raise VerificationError(
            f"예상하지 않은 wheel tag입니다: {wheel_metadata.get_all('Tag', [])!r}"
        )


def verify_sdist(path: Path, project_name: str, version: str) -> None:
    distribution = _normalized_distribution(project_name)
    expected_filename = f"{distribution}-{version}.tar.gz"
    if path.name != expected_filename:
        raise VerificationError(
            f"sdist 파일명이 예상과 다릅니다: {path.name!r} != {expected_filename!r}"
        )

    root = f"{distribution}-{version}"
    required = {
        f"{root}/LICENSE",
        f"{root}/README.md",
        f"{root}/pyproject.toml",
        f"{root}/tools/release/verify_artifacts.py",
        f"{root}/tools/web/build_site.py",
        f"{root}/web/app.js",
        f"{root}/web/index.html",
        f"{root}/web/py/bridge.py",
        f"{root}/web/styles.css",
        f"{root}/web/worker.js",
        *(f"{root}/src/{member}" for member in REQUIRED_PACKAGE_FILES),
    }
    with tarfile.open(path, "r:gz") as archive:
        members = {member.name.rstrip("/") for member in archive.getmembers()}
    missing = sorted(required.difference(members))
    if missing:
        raise VerificationError(f"sdist에 필수 파일이 없습니다: {', '.join(missing)}")


def verify_dist(dist_dir: Path, project_name: str, version: str) -> tuple[Path, Path]:
    wheels = sorted(dist_dir.glob("*.whl"))
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise VerificationError(
            "dist에는 wheel 1개와 sdist 1개만 있어야 합니다: "
            f"wheel={len(wheels)}, sdist={len(sdists)}"
        )
    verify_wheel(wheels[0], project_name, version)
    verify_sdist(sdists[0], project_name, version)
    return wheels[0], sdists[0]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dist-dir",
        type=Path,
        default=PROJECT_ROOT / "dist",
        help="python -m build 산출물 디렉터리",
    )
    parser.add_argument(
        "--source-only",
        action="store_true",
        help="소스의 패키지 버전 일치만 검증",
    )
    parser.add_argument(
        "--print-version",
        action="store_true",
        help="성공 시 버전 문자열만 출력",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        project_name, version = verify_source_versions()
        if not args.source_only:
            wheel, sdist = verify_dist(args.dist_dir.resolve(), project_name, version)
    except (OSError, VerificationError, tarfile.TarError, zipfile.BadZipFile) as error:
        print(f"release verification failed: {error}", file=sys.stderr)
        return 1

    if args.print_version:
        print(version)
    elif args.source_only:
        print(f"source version verified: {project_name} {version}")
    else:
        print(f"release artifacts verified: {wheel.name}, {sdist.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
