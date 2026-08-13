from pathlib import Path
import tempfile
import unittest

from tools.release.verify_artifacts import (
    VerificationError,
    _forbidden_wheel_members,
    verify_source_versions,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ReleaseSourceVersionTests(unittest.TestCase):
    def test_repository_versions_match(self):
        # Given
        root = PROJECT_ROOT
        # When
        name, version = verify_source_versions(root)
        # Then
        self.assertEqual(name, "k-safeguard")
        self.assertRegex(version, r"^\d+\.\d+\.\d+")

    def test_version_mismatch_is_rejected(self):
        # Given
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "src" / "k_safeguard").mkdir(parents=True)
            (root / "pyproject.toml").write_text(
                '[project]\nname = "k-safeguard"\nversion = "0.2.0"\n',
                encoding="utf-8",
            )
            (root / "src" / "k_safeguard" / "__init__.py").write_text(
                '__version__ = "0.1.0"\n',
                encoding="utf-8",
            )

            # When / Then
            with self.assertRaisesRegex(VerificationError, "배포 버전 불일치"):
                verify_source_versions(root)

    def test_wheel_boundary_rejects_models_datasets_and_experiments(self):
        # Given
        members = [
            "k_safeguard/gateway.py",
            "experiments/result.json",
            "k_safeguard/model.safetensors",
            "k_safeguard/seeds.csv",
        ]
        # When
        forbidden = _forbidden_wheel_members(members)
        # Then
        self.assertEqual(
            forbidden,
            [
                "experiments/result.json",
                "k_safeguard/model.safetensors",
                "k_safeguard/seeds.csv",
            ],
        )


if __name__ == "__main__":
    unittest.main()
