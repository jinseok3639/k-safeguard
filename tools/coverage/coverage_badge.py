"""coverage.xml에서 분기 커버리지를 뽑아 배지 데이터와 요약 마크다운을 만든다.

README의 shields.io endpoint 배지는 "공개된 URL의 JSON"을 읽어 이미지를 그린다.
이 스크립트가 그 JSON(`--badge-out`)과, PR 코멘트·job summary에 붙일 마크다운
표(`--markdown-out`)를 함께 생성한다.

외부 패키지 없이 Python 3.10 이상에서 실행할 수 있도록 표준 라이브러리만 쓴다.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sys
from xml.etree import ElementTree


CONDITION_COVERAGE = re.compile(r"\((?P<covered>\d+)/(?P<valid>\d+)\)")

# shields.io가 쓰는 관용적인 커버리지 색 구간. 높은 쪽부터 검사한다.
COLOR_THRESHOLDS = (
    (95.0, "brightgreen"),
    (90.0, "green"),
    (80.0, "yellowgreen"),
    (70.0, "yellow"),
    (60.0, "orange"),
)
FALLBACK_COLOR = "red"

MAX_LISTED_FILES = 10


class CoverageReportError(RuntimeError):
    """coverage.xml을 읽거나 해석하지 못했다."""


@dataclass(frozen=True)
class FileBranches:
    """파일 하나의 분기 측정값."""

    filename: str
    covered: int
    valid: int

    @property
    def rate(self) -> float:
        return _percent(self.covered, self.valid)

    @property
    def missing(self) -> int:
        return self.valid - self.covered


@dataclass(frozen=True)
class CoverageSummary:
    """coverage.xml 루트에 기록된 전체 측정값."""

    lines_covered: int
    lines_valid: int
    branches_covered: int
    branches_valid: int
    files: tuple[FileBranches, ...] = ()

    @property
    def line_rate(self) -> float:
        return _percent(self.lines_covered, self.lines_valid)

    @property
    def branch_rate(self) -> float:
        return _percent(self.branches_covered, self.branches_valid)

    @property
    def files_missing_branches(self) -> tuple[FileBranches, ...]:
        return tuple(
            sorted(
                (item for item in self.files if item.missing > 0),
                key=lambda item: (-item.missing, item.filename),
            )
        )


def _percent(covered: int, valid: int) -> float:
    """측정 대상이 없으면 coverage.py와 같이 100%로 본다."""

    if valid <= 0:
        return 100.0
    return covered / valid * 100.0


def format_percent(percent: float) -> str:
    """정수에 가까우면 소수점을 떼고, 아니면 소수 첫째 자리까지 보여준다."""

    if abs(percent - round(percent)) < 0.05:
        return f"{round(percent):d}%"
    return f"{percent:.1f}%"


def badge_color(percent: float) -> str:
    for threshold, color in COLOR_THRESHOLDS:
        if percent >= threshold:
            return color
    return FALLBACK_COLOR


def _int_attribute(element: ElementTree.Element, name: str) -> int:
    raw = element.get(name)
    if raw is None:
        raise CoverageReportError(f"coverage.xml 루트에 {name!r} 속성이 없습니다.")
    try:
        return int(raw)
    except ValueError as error:
        raise CoverageReportError(
            f"coverage.xml의 {name!r} 값이 정수가 아닙니다: {raw!r}"
        ) from error


def _file_branches(root: ElementTree.Element) -> tuple[FileBranches, ...]:
    """클래스별 <line branch="true" condition-coverage="50% (1/2)">를 합산한다."""

    files: list[FileBranches] = []
    for class_element in root.iter("class"):
        filename = class_element.get("filename")
        if filename is None:
            continue
        covered = 0
        valid = 0
        for line in class_element.iter("line"):
            if line.get("branch") != "true":
                continue
            match = CONDITION_COVERAGE.search(line.get("condition-coverage", ""))
            if match is None:
                continue
            covered += int(match.group("covered"))
            valid += int(match.group("valid"))
        files.append(FileBranches(filename=filename, covered=covered, valid=valid))
    return tuple(sorted(files, key=lambda item: item.filename))


def parse_coverage(xml_path: Path) -> CoverageSummary:
    try:
        tree = ElementTree.parse(xml_path)
    except ElementTree.ParseError as error:
        raise CoverageReportError(
            f"{xml_path}를 XML로 읽지 못했습니다: {error}"
        ) from error
    root = tree.getroot()
    return CoverageSummary(
        lines_covered=_int_attribute(root, "lines-covered"),
        lines_valid=_int_attribute(root, "lines-valid"),
        branches_covered=_int_attribute(root, "branches-covered"),
        branches_valid=_int_attribute(root, "branches-valid"),
        files=_file_branches(root),
    )


def badge_payload(
    summary: CoverageSummary, label: str = "branch coverage"
) -> dict[str, object]:
    """shields.io endpoint 스키마(https://shields.io/badges/endpoint-badge)."""

    return {
        "schemaVersion": 1,
        "label": label,
        "message": format_percent(summary.branch_rate),
        "color": badge_color(summary.branch_rate),
    }


def summary_markdown(summary: CoverageSummary) -> str:
    lines = [
        "### 커버리지",
        "",
        "| 항목 | 커버리지 | 측정 |",
        "|---|---:|---:|",
        f"| 분기 | {format_percent(summary.branch_rate)} | "
        f"{summary.branches_covered}/{summary.branches_valid} |",
        f"| 라인 | {format_percent(summary.line_rate)} | "
        f"{summary.lines_covered}/{summary.lines_valid} |",
        "",
    ]

    missing = summary.files_missing_branches
    if not missing:
        lines.append("측정 대상의 모든 분기가 커버됐습니다.")
        return "\n".join(lines) + "\n"

    total_missing = sum(item.missing for item in missing)
    lines.extend(
        [
            f"미커버 분기 {total_missing}개:",
            "",
            "| 파일 | 분기 커버리지 | 미커버 |",
            "|---|---:|---:|",
        ]
    )
    for item in missing[:MAX_LISTED_FILES]:
        lines.append(
            f"| `{item.filename}` | {format_percent(item.rate)} | "
            f"{item.missing}/{item.valid} |"
        )
    if len(missing) > MAX_LISTED_FILES:
        lines.append("")
        lines.append(f"…그 밖에 {len(missing) - MAX_LISTED_FILES}개 파일.")
    return "\n".join(lines) + "\n"


def github_outputs(summary: CoverageSummary) -> str:
    """워크플로 후속 스텝이 쓸 수 있게 GITHUB_OUTPUT 형식으로 만든다."""

    return "".join(
        f"{key}={value}\n"
        for key, value in (
            ("branch_rate", f"{summary.branch_rate:.2f}"),
            ("branch_percent", format_percent(summary.branch_rate)),
            ("branches_covered", str(summary.branches_covered)),
            ("branches_valid", str(summary.branches_valid)),
            ("line_rate", f"{summary.line_rate:.2f}"),
            ("line_percent", format_percent(summary.line_rate)),
            ("lines_covered", str(summary.lines_covered)),
            ("lines_valid", str(summary.lines_valid)),
        )
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--xml",
        type=Path,
        default=Path("coverage.xml"),
        help="coverage xml 리포트 경로 (기본: coverage.xml)",
    )
    parser.add_argument(
        "--badge-out",
        type=Path,
        help="shields.io endpoint 배지 JSON을 쓸 경로",
    )
    parser.add_argument(
        "--markdown-out",
        type=Path,
        help="PR 코멘트·job summary용 마크다운을 쓸 경로",
    )
    parser.add_argument(
        "--label",
        default="branch coverage",
        help="배지 왼쪽 라벨 (기본: branch coverage)",
    )
    parser.add_argument(
        "--github-output",
        action="store_true",
        help="GITHUB_OUTPUT 환경변수가 가리키는 파일에 측정값을 덧붙인다",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summary = parse_coverage(args.xml)
    except (OSError, CoverageReportError) as error:
        print(f"coverage badge failed: {error}", file=sys.stderr)
        return 1

    if args.badge_out is not None:
        _write(
            args.badge_out,
            json.dumps(badge_payload(summary, args.label), ensure_ascii=False) + "\n",
        )
    if args.markdown_out is not None:
        _write(args.markdown_out, summary_markdown(summary))
    if args.github_output:
        output_path = os.environ.get("GITHUB_OUTPUT")
        if not output_path:
            print(
                "coverage badge failed: GITHUB_OUTPUT이 설정되지 않았습니다.",
                file=sys.stderr,
            )
            return 1
        with open(output_path, "a", encoding="utf-8") as handle:
            handle.write(github_outputs(summary))

    print(
        "branch coverage "
        f"{format_percent(summary.branch_rate)} "
        f"({summary.branches_covered}/{summary.branches_valid}), "
        "line coverage "
        f"{format_percent(summary.line_rate)} "
        f"({summary.lines_covered}/{summary.lines_valid})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
