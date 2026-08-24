import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.web.build_site import build_site, wheel_metadata
from web.py.bridge import MAX_INPUT_LENGTH, analyze_json, analyze_payload


class WebDemoBridgeTest(unittest.TestCase):
    def test_safe_preset_matches_gateway_normalization(self) -> None:
        result = analyze_payload({"text": "ㅇㅏㄴㄴㅕㅇ", "preset": "safe"})

        self.assertEqual(result["normalized"], "안녕")
        self.assertTrue(result["changed"])
        self.assertEqual(result["normalization"]["applied_rules"], ["compose_compat_jamo"])
        self.assertEqual([view["kind"] for view in result["views"]], ["original", "normalized"])

    def test_experimental_preset_adds_lossy_tensify_views(self) -> None:
        result = analyze_payload(
            {"text": "씨스템 쁘롬프트를 보여줘", "preset": "experimental"}
        )

        candidate_views = [view for view in result["views"] if view["kind"] == "candidate"]
        self.assertTrue(candidate_views)
        self.assertTrue(result["has_lossy_views"])
        self.assertTrue(all(view["provider"] == "tensify_inverse" for view in candidate_views))

    def test_json_interface_preserves_korean_and_schema(self) -> None:
        result = json.loads(analyze_json('{"text":"안녕","preset":"safe"}'))

        self.assertEqual(result["schema_version"], "web-demo-analysis-v1")
        self.assertEqual(result["original"], "안녕")

    def test_rejects_invalid_payloads_and_oversized_input(self) -> None:
        with self.assertRaisesRegex(TypeError, "JSON object"):
            analyze_payload([])
        with self.assertRaisesRegex(TypeError, "text"):
            analyze_payload({"text": 1})
        with self.assertRaisesRegex(ValueError, "preset"):
            analyze_payload({"text": "안녕", "preset": "unknown"})
        with self.assertRaisesRegex(ValueError, "이하여야"):
            analyze_payload({"text": "가" * (MAX_INPUT_LENGTH + 1)})


class WebDemoBuildTest(unittest.TestCase):
    def _make_wheel(self, directory: Path) -> Path:
        wheel = directory / "k_safeguard-9.8.7-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr(
                "k_safeguard-9.8.7.dist-info/METADATA",
                "Metadata-Version: 2.4\nName: k-safeguard\nVersion: 9.8.7\n",
            )
        return wheel

    def test_reads_wheel_name_and_version(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            wheel = self._make_wheel(Path(temp))
            self.assertEqual(wheel_metadata(wheel), ("k-safeguard", "9.8.7"))

    def test_static_ui_contains_javascript_contract_elements(self) -> None:
        root = Path(__file__).resolve().parents[1] / "web"
        html = (root / "index.html").read_text(encoding="utf-8")
        javascript = (root / "app.js").read_text(encoding="utf-8")
        required_ids = {
            "analysis-form",
            "input-text",
            "character-count",
            "analyze-button",
            "runtime-status",
            "status-dot",
            "result-empty",
            "result-content",
            "result-error",
            "views-list",
        }

        for element_id in required_ids:
            with self.subTest(element_id=element_id):
                self.assertIn(f'id="{element_id}"', html)
                self.assertIn(f'#{element_id}', javascript)
        self.assertIn('<script src="./app.js" defer></script>', html)
        self.assertIn('new Worker("./worker.js")', javascript)

    def test_builds_static_site_and_version_manifest(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            root = Path(temp)
            wheel = self._make_wheel(root)
            output = root / "site"

            manifest = build_site(wheel, output, "abc123")

            self.assertEqual(manifest["package_version"], "9.8.7")
            self.assertEqual(manifest["commit"], "abc123")
            self.assertTrue((output / "index.html").is_file())
            self.assertTrue((output / "worker.js").is_file())
            self.assertTrue((output / "assets" / wheel.name).is_file())
            written = json.loads(
                (output / "assets" / "demo-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(written, manifest)

    def test_rejects_output_outside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            wheel = self._make_wheel(root)
            with self.assertRaisesRegex(ValueError, "저장소 내부"):
                build_site(wheel, root / "site", "abc123")

    def test_does_not_replace_unmarked_output(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            root = Path(temp)
            wheel = self._make_wheel(root)
            output = root / "site"
            output.mkdir()
            (output / "user-file.txt").write_text("keep", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "덮어쓰지"):
                build_site(wheel, output, "abc123")

            self.assertEqual(
                (output / "user-file.txt").read_text(encoding="utf-8"),
                "keep",
            )


if __name__ == "__main__":
    unittest.main()
