"""`MlRestoreProvider.from_pretrained()`가 쓰는 다운로드·캐시·검증 로직 테스트.

`urllib.request.urlopen`을 몽키패치해 실제 네트워크 없이 돈다. onnxruntime 세션을
실제로 만들지 않으므로 extra 없이도 통과한다 — `from_pretrained()` 전체(진짜 가중치를
받아 provider를 완성하는 것)의 종단 간 검증은 `from_directory()`와 같은 이유로 여기
없다: 실제 가중치가 저장소에 없다. 그건 ML 샌드박스의 `exp/verify_port_parity.py`가
로컬 HTTP 서버로 재현해서 확인한다.
"""

import hashlib
import io
import unittest
import urllib.error
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from k_safeguard.providers import ml_restore as module


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class _FakeResponse(io.BytesIO):
    """`urllib.request.urlopen`이 돌려주는 context manager를 흉내낸다."""

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class VerifyFileTest(unittest.TestCase):
    def test_accepts_file_matching_size_and_hash(self) -> None:
        # Given
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.bin"
            data = b"hello weights"
            path.write_bytes(data)
            # When / Then — 예외가 안 나야 한다
            module._verify_file(
                path, sha256=_sha256(data), size=len(data), source="test"
            )
            self.assertTrue(path.exists())

    def test_rejects_and_deletes_file_with_wrong_size(self) -> None:
        # Given
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.bin"
            path.write_bytes(b"short")
            # When / Then
            with self.assertRaises(RuntimeError):
                module._verify_file(path, sha256="x" * 64, size=999, source="test")
            self.assertFalse(path.exists())

    def test_rejects_and_deletes_file_with_wrong_hash(self) -> None:
        # Given
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.bin"
            data = b"tampered"
            path.write_bytes(data)
            # When / Then
            with self.assertRaises(RuntimeError):
                module._verify_file(
                    path, sha256="0" * 64, size=len(data), source="test"
                )
            self.assertFalse(path.exists())


class DownloadFileTest(unittest.TestCase):
    def test_writes_file_when_content_matches_manifest(self) -> None:
        # Given
        data = b"valid onnx bytes"
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "nested" / "tensify.onnx"
            # When
            with mock.patch.object(
                module.urllib.request, "urlopen", return_value=_FakeResponse(data)
            ):
                module._download_file(
                    "http://example.invalid/tensify.onnx",
                    dest,
                    sha256=_sha256(data),
                    size=len(data),
                )
            # Then
            self.assertEqual(dest.read_bytes(), data)
            self.assertFalse(dest.with_name(dest.name + ".part").exists())

    def test_rejects_corrupted_download_and_removes_partial_file(self) -> None:
        # Given — 서버 응답이 manifest의 해시와 다르다(전송 중 손상 흉내)
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "tensify.onnx"
            # When / Then
            with mock.patch.object(
                module.urllib.request,
                "urlopen",
                return_value=_FakeResponse(b"corrupted"),
            ):
                with self.assertRaises(RuntimeError):
                    module._download_file(
                        "http://example.invalid/tensify.onnx",
                        dest,
                        sha256=_sha256(b"expected"),
                        size=len(b"expected"),
                    )
            self.assertFalse(dest.exists())
            self.assertFalse(dest.with_name(dest.name + ".part").exists())

    def test_wraps_network_failure_as_runtime_error(self) -> None:
        # Given
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "tensify.onnx"
            # When / Then
            with mock.patch.object(
                module.urllib.request,
                "urlopen",
                side_effect=urllib.error.URLError("연결 실패"),
            ):
                with self.assertRaisesRegex(RuntimeError, "다운로드 실패"):
                    module._download_file(
                        "http://example.invalid/tensify.onnx",
                        dest,
                        sha256="0" * 64,
                        size=1,
                    )
            self.assertFalse(dest.exists())


class DefaultCacheDirTest(unittest.TestCase):
    """`os.name`을 다른 값으로 흉내내지 않는다 — 최신 pathlib은 실행 중인 OS와

    다른 `Path` 플레이버(`PosixPath` on Windows 등) 생성을 막는다. 대신 실제
    실행 OS의 분기를 그 OS의 실제 환경변수로 검증한다. 나머지 OS 분기는 CI의
    3-OS 매트릭스(`package.yml`)가 각자의 네이티브 환경에서 돈다.
    """

    def test_native_branch_uses_the_platform_specific_env_var(self) -> None:
        # Given
        env_var = "LOCALAPPDATA" if module.os.name == "nt" else "XDG_CACHE_HOME"
        base = "C:\\fake\\cache" if module.os.name == "nt" else "/fake/cache"
        # When
        with mock.patch.dict(module.os.environ, {env_var: base}):
            cache_dir = module._default_cache_dir()
        # Then
        self.assertEqual(
            cache_dir, Path(base) / "k-safeguard" / "ml-restore" / module.PRETRAINED_TAG
        )

    def test_falls_back_to_home_directory_when_env_var_is_unset(self) -> None:
        # Given
        env_var = "LOCALAPPDATA" if module.os.name == "nt" else "XDG_CACHE_HOME"
        # When
        with mock.patch.dict(module.os.environ, {}, clear=False):
            module.os.environ.pop(env_var, None)
            cache_dir = module._default_cache_dir()
        # Then — 어디든 좋으니 크래시 없이 경로를 만들어야 한다
        self.assertTrue(cache_dir.is_absolute())

    def test_cache_dir_is_pinned_to_the_release_tag(self) -> None:
        # Given / When
        cache_dir = module._default_cache_dir()
        # Then — 릴리스가 바뀌면 캐시 경로도 바뀌어 옛 가중치와 안 섞인다
        self.assertEqual(cache_dir.name, module.PRETRAINED_TAG)


class PretrainedManifestTest(unittest.TestCase):
    def test_every_entry_has_the_fields_from_entries_needs(self) -> None:
        # Given / When / Then
        for technique, entry in module.PRETRAINED_MANIFEST.items():
            for key in (
                "threshold", "window", "onnx_file", "onnx_sha256", "onnx_bytes",
                "vocab_file", "vocab_sha256", "vocab_bytes",
            ):
                self.assertIn(key, entry, f"{technique}에 {key} 없음")
            self.assertEqual(len(entry["onnx_sha256"]), 64)
            self.assertEqual(len(entry["vocab_sha256"]), 64)
            self.assertTrue(0.0 <= entry["threshold"] <= 1.0)

    def test_matches_the_techniques_the_provider_ships(self) -> None:
        # Given / When / Then
        self.assertEqual(set(module.PRETRAINED_MANIFEST), set(module.DEFAULT_ORDER))


if __name__ == "__main__":
    unittest.main()
