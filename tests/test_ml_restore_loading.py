"""`from_directory()` / `from_pretrained()`의 로딩 제어 흐름 테스트.

런타임 패키지를 가짜 모듈로 끼워 넣어 extra 없이 돈다. 실제 ONNX 추론이 아니라 manifest
해석·검증·오류 처리 경로만 본다.
"""

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from k_safeguard.providers import ml_restore as module


class _FakeSession:
    def __init__(self, path, providers=None):
        self.path = path
        self.providers = providers


class _FakeTokenizer:
    @classmethod
    def from_file(cls, path):
        return cls()


_FAKE_MODULES = {
    "numpy": SimpleNamespace(),
    "onnxruntime": SimpleNamespace(InferenceSession=_FakeSession),
    "tokenizers": SimpleNamespace(Tokenizer=_FakeTokenizer),
}


def _manifest(**overrides) -> dict:
    manifest = {
        "threshold": 0.65,
        "max_chars": 384,
        "files": {
            "model": {"file": "m.onnx"},
            "tokenizer": {"file": "t.json"},
            "char_vocab": {"file": "v.json"},
        },
    }
    manifest.update(overrides)
    return manifest


def _write_weights(root: Path, manifest: dict) -> None:
    for entry in manifest["files"].values():
        (root / entry["file"]).write_text("{}", encoding="utf-8")
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _fill_cache(root: Path) -> None:
    """캐시 히트 조건(크기 일치)을 만족하는 파일을 만든다."""
    for entry in module.PRETRAINED_MANIFEST["files"].values():
        body = b"{}" + b" " * (entry["bytes"] - 2)
        (root / entry["file"]).write_bytes(body)


def _fake_download(url, dest, *, sha256, size):
    dest.write_text("{}", encoding="utf-8")


class _FakeRuntimeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.dict(sys.modules, _FAKE_MODULES)
        patcher.start()
        self.addCleanup(patcher.stop)


class FromDirectoryTest(_FakeRuntimeTestCase):
    def test_missing_manifest_raises_file_not_found(self) -> None:
        # Given / When / Then
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(FileNotFoundError, "manifest"):
                module.MlRestoreProvider.from_directory(tmp)

    def test_missing_threshold_is_rejected_instead_of_defaulting_to_zero(self) -> None:
        # Given — threshold가 0.0으로 조용히 떨어지면 abstention이 통째로 꺼진다
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = _manifest()
            del manifest["threshold"]
            _write_weights(root, manifest)
            # When / Then
            with self.assertRaisesRegex(ValueError, "threshold"):
                module.MlRestoreProvider.from_directory(root)

    def test_non_numeric_threshold_is_rejected(self) -> None:
        # Given
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_weights(root, _manifest(threshold="높게"))
            # When / Then
            with self.assertRaisesRegex(ValueError, "숫자가 아닙니다"):
                module.MlRestoreProvider.from_directory(root)

    def test_out_of_range_threshold_is_rejected(self) -> None:
        # Given
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_weights(root, _manifest(threshold=1.5))
            # When / Then
            with self.assertRaisesRegex(ValueError, "0~1"):
                module.MlRestoreProvider.from_directory(root)

    def test_missing_max_chars_is_rejected(self) -> None:
        # Given
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = _manifest()
            del manifest["max_chars"]
            _write_weights(root, manifest)
            # When / Then
            with self.assertRaisesRegex(ValueError, "max_chars"):
                module.MlRestoreProvider.from_directory(root)

    def test_manifest_without_a_file_role_is_rejected(self) -> None:
        # Given
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = _manifest()
            _write_weights(root, manifest)
            del manifest["files"]["tokenizer"]
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            # When / Then
            with self.assertRaisesRegex(ValueError, "tokenizer"):
                module.MlRestoreProvider.from_directory(root)

    def test_missing_weight_file_raises_file_not_found(self) -> None:
        # Given — manifest는 있는데 가리키는 모델이 없다
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = _manifest()
            _write_weights(root, manifest)
            (root / "m.onnx").unlink()
            # When / Then
            with self.assertRaisesRegex(FileNotFoundError, "가중치 파일"):
                module.MlRestoreProvider.from_directory(root)

    def test_explicit_threshold_overrides_the_manifest(self) -> None:
        # Given
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_weights(root, _manifest())
            # When
            provider = module.MlRestoreProvider.from_directory(root, threshold=0.5)
            # Then
            self.assertEqual(provider.threshold, 0.5)

    def test_uses_the_cpu_execution_provider(self) -> None:
        # Given
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_weights(root, _manifest())
            # When
            provider = module.MlRestoreProvider.from_directory(root)
            # Then
            self.assertEqual(provider._tagger._session.providers, ["CPUExecutionProvider"])

    def test_missing_runtime_points_at_the_extra(self) -> None:
        # Given — sys.modules의 None은 import를 ImportError로 만든다
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_weights(root, _manifest())
            # When / Then
            with mock.patch.dict(sys.modules, {"tokenizers": None}):
                with self.assertRaisesRegex(ImportError, "ml-restore"):
                    module.MlRestoreProvider.from_directory(root)


class FromPretrainedTest(_FakeRuntimeTestCase):
    def test_missing_runtime_fails_before_any_download(self) -> None:
        # Given / When / Then
        with mock.patch.object(module, "_download_file") as download:
            with mock.patch.dict(sys.modules, {"onnxruntime": None}):
                with self.assertRaisesRegex(ImportError, "ml-restore"):
                    module.MlRestoreProvider.from_pretrained()
        download.assert_not_called()

    def test_cached_file_of_matching_size_is_not_redownloaded(self) -> None:
        # Given — 캐시에 선언된 크기와 같은 파일이 이미 있다
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            sizes = {"model": 4, "tokenizer": 4, "char_vocab": 4}
            files = {
                role: {**entry, "bytes": sizes[role]}
                for role, entry in module.PRETRAINED_MANIFEST["files"].items()
            }
            with mock.patch.dict(module.PRETRAINED_MANIFEST, {"files": files}):
                _fill_cache(root)
                # When
                with mock.patch.object(module, "_download_file") as download:
                    module.MlRestoreProvider.from_pretrained(cache_dir=root)
            # Then
            download.assert_not_called()

    def test_force_download_refetches_even_when_cached(self) -> None:
        # Given
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            # When
            with mock.patch.object(
                module, "_download_file", side_effect=_fake_download
            ) as download:
                module.MlRestoreProvider.from_pretrained(
                    cache_dir=root, force_download=True
                )
            # Then — 모델·토크나이저·어휘 모두 다시 받는다
            self.assertEqual(download.call_count, 3)

    def test_download_url_points_at_the_pinned_release_over_https(self) -> None:
        # Given
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            urls = []

            def record(url, dest, *, sha256, size):
                urls.append(url)
                _fake_download(url, dest, sha256=sha256, size=size)

            # When
            with mock.patch.object(module, "_download_file", record):
                module.MlRestoreProvider.from_pretrained(cache_dir=root)
            # Then
            self.assertEqual(len(urls), 3)
            for url in urls:
                self.assertTrue(url.startswith("https://"))
                self.assertIn(module.PRETRAINED_REPO, url)
                self.assertIn(module.PRETRAINED_TAG, url)


if __name__ == "__main__":
    unittest.main()
