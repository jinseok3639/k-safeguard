import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools.coverage.coverage_badge import (
    CoverageReportError,
    CoverageSummary,
    FileBranches,
    badge_color,
    badge_payload,
    format_percent,
    github_outputs,
    main,
    parse_coverage,
    summary_markdown,
)


FULLY_COVERED_XML = """<?xml version="1.0" ?>
<coverage version="7.15.4" lines-valid="10" lines-covered="10" line-rate="1"
          branches-valid="4" branches-covered="4" branch-rate="1">
  <packages>
    <classes>
      <class filename="src/k_safeguard/gateway.py">
        <lines>
          <line number="1" hits="1"/>
          <line number="2" hits="1" branch="true" condition-coverage="100% (2/2)"/>
          <line number="9" hits="1" branch="true" condition-coverage="100% (2/2)"/>
        </lines>
      </class>
    </classes>
  </packages>
</coverage>
"""

PARTIAL_XML = """<?xml version="1.0" ?>
<coverage version="7.15.4" lines-valid="200" lines-covered="184" line-rate="0.92"
          branches-valid="50" branches-covered="46" branch-rate="0.92">
  <packages>
    <classes>
      <class filename="src/k_safeguard/gateway.py">
        <lines>
          <line number="2" hits="1" branch="true" condition-coverage="50% (1/2)"/>
          <line number="7" hits="1" branch="true" condition-coverage="50% (1/2)"/>
          <line number="8" hits="1" branch="true" condition-coverage="100% (2/2)"/>
        </lines>
      </class>
      <class filename="src/k_safeguard/normalization.py">
        <lines>
          <line number="3" hits="1"/>
          <line number="4" hits="1" branch="true" condition-coverage="50% (1/2)"/>
        </lines>
      </class>
      <class filename="src/k_safeguard/chosung.py">
        <lines>
          <line number="5" hits="1" branch="true" condition-coverage="100% (2/2)"/>
        </lines>
      </class>
    </classes>
  </packages>
</coverage>
"""

MISSING_ATTRIBUTE_XML = """<?xml version="1.0" ?>
<coverage version="7.15.4" lines-valid="10" lines-covered="10" line-rate="1"/>
"""


@contextlib.contextmanager
def _quiet():
    """main()의 진행 출력이 테스트 결과에 섞이지 않게 한다."""

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        yield buffer


def _write_xml(directory: Path, text: str) -> Path:
    path = directory / "coverage.xml"
    path.write_text(text, encoding="utf-8")
    return path


class CoverageParsingTests(unittest.TestCase):
    def test_totals_and_per_file_branches_are_parsed(self):
        # Given
        with tempfile.TemporaryDirectory() as temp_dir:
            xml_path = _write_xml(Path(temp_dir), PARTIAL_XML)

            # When
            summary = parse_coverage(xml_path)

            # Then
            self.assertEqual(summary.branches_covered, 46)
            self.assertEqual(summary.branches_valid, 50)
            self.assertEqual(summary.lines_covered, 184)
            self.assertAlmostEqual(summary.branch_rate, 92.0)
            self.assertEqual(
                [item.filename for item in summary.files],
                [
                    "src/k_safeguard/chosung.py",
                    "src/k_safeguard/gateway.py",
                    "src/k_safeguard/normalization.py",
                ],
            )

    def test_files_missing_branches_sorted_by_missing_count(self):
        # Given
        with tempfile.TemporaryDirectory() as temp_dir:
            xml_path = _write_xml(Path(temp_dir), PARTIAL_XML)

            # When
            missing = parse_coverage(xml_path).files_missing_branches

            # Then: 완전 커버된 chosung.py는 빠지고, 미커버가 많은 쪽이 먼저 온다
            self.assertEqual(
                [(item.filename, item.missing) for item in missing],
                [
                    ("src/k_safeguard/gateway.py", 2),
                    ("src/k_safeguard/normalization.py", 1),
                ],
            )

    def test_missing_root_attribute_is_rejected(self):
        # Given
        with tempfile.TemporaryDirectory() as temp_dir:
            xml_path = _write_xml(Path(temp_dir), MISSING_ATTRIBUTE_XML)

            # When / Then
            with self.assertRaisesRegex(CoverageReportError, "branches-covered"):
                parse_coverage(xml_path)

    def test_broken_xml_is_rejected(self):
        # Given
        with tempfile.TemporaryDirectory() as temp_dir:
            xml_path = _write_xml(Path(temp_dir), "<coverage")

            # When / Then
            with self.assertRaisesRegex(CoverageReportError, "XML로 읽지 못했습니다"):
                parse_coverage(xml_path)


class RateFormattingTests(unittest.TestCase):
    def test_no_measurable_branches_counts_as_full_coverage(self):
        # Given
        summary = CoverageSummary(
            lines_covered=0, lines_valid=0, branches_covered=0, branches_valid=0
        )
        # When / Then
        self.assertEqual(summary.branch_rate, 100.0)
        self.assertEqual(summary.line_rate, 100.0)

    def test_integral_percent_drops_decimals(self):
        # Given / When / Then
        self.assertEqual(format_percent(100.0), "100%")
        self.assertEqual(format_percent(92.0), "92%")

    def test_fractional_percent_keeps_one_decimal(self):
        # Given / When / Then
        self.assertEqual(format_percent(92.34), "92.3%")
        self.assertEqual(format_percent(66.666), "66.7%")

    def test_badge_color_follows_thresholds(self):
        # Given / When / Then
        self.assertEqual(badge_color(100.0), "brightgreen")
        self.assertEqual(badge_color(95.0), "brightgreen")
        self.assertEqual(badge_color(94.9), "green")
        self.assertEqual(badge_color(89.9), "yellowgreen")
        self.assertEqual(badge_color(79.9), "yellow")
        self.assertEqual(badge_color(69.9), "orange")
        self.assertEqual(badge_color(59.9), "red")


class BadgePayloadTests(unittest.TestCase):
    def test_payload_uses_shields_endpoint_schema(self):
        # Given
        summary = CoverageSummary(
            lines_covered=10, lines_valid=10, branches_covered=4, branches_valid=4
        )
        # When
        payload = badge_payload(summary)
        # Then
        self.assertEqual(
            payload,
            {
                "schemaVersion": 1,
                "label": "branch coverage",
                "message": "100%",
                "color": "brightgreen",
            },
        )

    def test_label_is_configurable(self):
        # Given
        summary = CoverageSummary(
            lines_covered=1, lines_valid=2, branches_covered=1, branches_valid=2
        )
        # When
        payload = badge_payload(summary, label="분기 커버리지")
        # Then
        self.assertEqual(payload["label"], "분기 커버리지")
        self.assertEqual(payload["message"], "50%")
        self.assertEqual(payload["color"], "red")


class SummaryMarkdownTests(unittest.TestCase):
    def test_full_coverage_reports_no_missing_branches(self):
        # Given
        with tempfile.TemporaryDirectory() as temp_dir:
            summary = parse_coverage(_write_xml(Path(temp_dir), FULLY_COVERED_XML))

            # When
            markdown = summary_markdown(summary)

            # Then
            self.assertIn("| 분기 | 100% | 4/4 |", markdown)
            self.assertIn("| 라인 | 100% | 10/10 |", markdown)
            self.assertIn("모든 분기가 커버됐습니다", markdown)
            self.assertNotIn("미커버 분기", markdown)

    def test_partial_coverage_lists_files_with_missing_branches(self):
        # Given
        with tempfile.TemporaryDirectory() as temp_dir:
            summary = parse_coverage(_write_xml(Path(temp_dir), PARTIAL_XML))

            # When
            markdown = summary_markdown(summary)

            # Then
            self.assertIn("| 분기 | 92% | 46/50 |", markdown)
            self.assertIn("미커버 분기 3개", markdown)
            self.assertIn("| `src/k_safeguard/gateway.py` | 66.7% | 2/6 |", markdown)
            self.assertNotIn("chosung.py", markdown)

    def test_long_file_list_is_truncated(self):
        # Given
        summary = CoverageSummary(
            lines_covered=0,
            lines_valid=0,
            branches_covered=0,
            branches_valid=24,
            files=tuple(
                FileBranches(filename=f"src/module_{index:02d}.py", covered=0, valid=2)
                for index in range(12)
            ),
        )
        # When
        markdown = summary_markdown(summary)
        # Then
        self.assertIn("…그 밖에 2개 파일.", markdown)
        self.assertIn("src/module_09.py", markdown)
        self.assertNotIn("src/module_11.py", markdown)


class GithubOutputTests(unittest.TestCase):
    def test_outputs_are_key_value_lines(self):
        # Given
        summary = CoverageSummary(
            lines_covered=184, lines_valid=200, branches_covered=46, branches_valid=50
        )
        # When
        rendered = dict(
            line.split("=", 1) for line in github_outputs(summary).splitlines()
        )
        # Then
        self.assertEqual(rendered["branch_rate"], "92.00")
        self.assertEqual(rendered["branch_percent"], "92%")
        self.assertEqual(rendered["branches_covered"], "46")
        self.assertEqual(rendered["branches_valid"], "50")
        self.assertEqual(rendered["line_percent"], "92%")
        self.assertEqual(rendered["lines_valid"], "200")


class CommandLineTests(unittest.TestCase):
    def test_main_writes_badge_json_and_markdown(self):
        # Given
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            xml_path = _write_xml(root, PARTIAL_XML)
            badge_path = root / "badge" / "branch-coverage.json"
            markdown_path = root / "summary.md"

            # When
            with _quiet():
                exit_code = main(
                    [
                        "--xml",
                        str(xml_path),
                        "--badge-out",
                        str(badge_path),
                        "--markdown-out",
                        str(markdown_path),
                    ]
                )

            # Then
            self.assertEqual(exit_code, 0)
            self.assertEqual(
                json.loads(badge_path.read_text(encoding="utf-8")),
                {
                    "schemaVersion": 1,
                    "label": "branch coverage",
                    "message": "92%",
                    "color": "green",
                },
            )
            self.assertIn("### 커버리지", markdown_path.read_text(encoding="utf-8"))

    def test_main_reports_missing_report_as_failure(self):
        # Given
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "nope.xml"

            # When
            with _quiet():
                exit_code = main(["--xml", str(missing)])

            # Then
            self.assertEqual(exit_code, 1)

    def test_github_output_requires_environment_variable(self):
        # Given
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            xml_path = _write_xml(root, FULLY_COVERED_XML)
            output_path = root / "outputs.txt"

            # When: 환경변수가 없으면 실패, 있으면 그 파일에 덧붙인다
            with _quiet(), mock.patch.dict("os.environ", {}, clear=True):
                without_env = main(["--xml", str(xml_path), "--github-output"])
            with _quiet(), mock.patch.dict(
                "os.environ", {"GITHUB_OUTPUT": str(output_path)}
            ):
                with_env = main(["--xml", str(xml_path), "--github-output"])

            # Then
            self.assertEqual(without_env, 1)
            self.assertEqual(with_env, 0)
            self.assertIn("branch_percent=100%", output_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
