"""`from_directory()` / `from_pretrained()`의 로딩 제어 흐름 테스트.

`onnxruntime`을 가짜 모듈로 끼워 넣어 extra 없이 돈다 — 실제 ONNX 추론이 아니라
manifest 해석·검증·오류 처리 경로만 본다. 복원 수치 자체의 정확성은 여기서 다루지
않는다(모듈 docstring 참고).
"""

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from k_safeguard.jamo_slots import PAD_CHAR, PAD_ID, UNK_ID
from k_safeguard.providers import ml_restore as module


class _FakeSession:
    """슬롯 수보다 넉넉한 출력을 가진 최소 ONNX 세션 stub."""

    def __init__(self, path, providers=None):
        self.path = path

    def get_outputs(self):
        return [object(), object(), object()]


class _FakeOnnxruntime:
    InferenceSession = _FakeSession


def _entry(**overrides) -> dict:
    entry = {
        "threshold": 0.99,
        "window": 4,
        "onnx_file": "t.onnx",
        "vocab_file": "t.vocab.json",
    }
    entry.update(overrides)
    return entry


def _padded_vocab(size: int) -> bytes:
    """정확히 `size` 바이트인 유효한 vocab JSON. 캐시 히트 조건(크기 일치)을 만들 때 쓴다."""
    body = json.dumps({PAD_CHAR: PAD_ID}).encode("utf-8")
    if len(body) > size:
        raise ValueError("요청한 크기가 최소 JSON 보다 작습니다.")
    return body + b" " * (size - len(body))


def _write_weights(root: Path, entries: dict) -> None:
    """manifest와 그 안에서 가리키는 파일들을 만든다."""
    for entry in entries.values():
        (root / entry["onnx_file"]).write_bytes(b"")
        (root / entry["vocab_file"]).write_text(
            json.dumps({PAD_CHAR: PAD_ID, "￿": UNK_ID}), encoding="utf-8"
        )
    (root / "manifest.json").write_text(
        json.dumps({"techniques": entries}), encoding="utf-8"
    )


class _FakeOnnxTestCase(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.dict(sys.modules, {"onnxruntime": _FakeOnnxruntime})
        patcher.start()
        self.addCleanup(patcher.stop)


class FromDirectoryTest(_FakeOnnxTestCase):
    def test_missing_manifest_raises_file_not_found(self) -> None:
        # Given / When / Then
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(FileNotFoundError, "manifest"):
                module.MlRestoreProvider.from_directory(tmp)

    def test_manifest_without_techniques_is_rejected(self) -> None:
        # Given
        with TemporaryDirectory() as tmp:
            (Path(tmp) / "manifest.json").write_text("{}", encoding="utf-8")
            # When / Then
            with self.assertRaisesRegex(ValueError, "기법이 없습니다"):
                module.MlRestoreProvider.from_directory(tmp)

    def test_missing_threshold_is_rejected_instead_of_defaulting_to_zero(self) -> None:
        # Given — threshold가 0.0으로 조용히 떨어지면 abstention이 통째로 꺼진다
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            entry = _entry()
            del entry["threshold"]
            _write_weights(root, {"tensify": entry})
            # When / Then
            with self.assertRaisesRegex(ValueError, "threshold"):
                module.MlRestoreProvider.from_directory(root)

    def test_non_numeric_threshold_is_rejected(self) -> None:
        # Given
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_weights(root, {"tensify": _entry(threshold="높게")})
            # When / Then
            with self.assertRaisesRegex(ValueError, "숫자가 아닙니다"):
                module.MlRestoreProvider.from_directory(root)

    def test_out_of_range_threshold_is_rejected(self) -> None:
        # Given
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_weights(root, {"tensify": _entry(threshold=1.5)})
            # When / Then
            with self.assertRaisesRegex(ValueError, "0~1"):
                module.MlRestoreProvider.from_directory(root)

    def test_missing_weight_file_raises_file_not_found(self) -> None:
        # Given — manifest는 있는데 가리키는 onnx가 없다
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            entry = _entry(onnx_file="gone.onnx")
            (root / entry["vocab_file"]).write_text(
                json.dumps({PAD_CHAR: PAD_ID}), encoding="utf-8"
            )
            (root / "manifest.json").write_text(
                json.dumps({"techniques": {"tensify": entry}}), encoding="utf-8"
            )
            # When / Then
            with self.assertRaisesRegex(FileNotFoundError, "가중치 파일"):
                module.MlRestoreProvider.from_directory(root)

    def test_selecting_a_technique_absent_from_the_manifest_is_rejected(self) -> None:
        # Given
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_weights(root, {"tensify": _entry()})
            # When / Then
            with self.assertRaisesRegex(ValueError, "없는 기법"):
                module.MlRestoreProvider.from_directory(root, techniques=("liaison",))

    def test_explicit_thresholds_override_the_manifest(self) -> None:
        # Given
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_weights(root, {"tensify": _entry(threshold=0.99)})
            # When
            provider = module.MlRestoreProvider.from_directory(
                root, thresholds={"tensify": 0.5}
            )
            # Then
            self.assertEqual(provider._restorers["tensify"].threshold, 0.5)

    def test_loads_every_technique_in_the_manifest_by_default(self) -> None:
        # Given
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_weights(
                root,
                {
                    "tensify": _entry(),
                    "liaison": _entry(
                        onnx_file="l.onnx", vocab_file="l.vocab.json"
                    ),
                },
            )
            # When
            provider = module.MlRestoreProvider.from_directory(root)
            # Then — 선언 순서가 아니라 DEFAULT_ORDER 우선순위를 따른다
            self.assertEqual(provider._order[:2], ("tensify", "liaison"))


class FromPretrainedTest(_FakeOnnxTestCase):
    def test_unknown_technique_is_rejected_before_any_download(self) -> None:
        # Given / When / Then
        with mock.patch.object(module, "_download_file") as download:
            with self.assertRaisesRegex(ValueError, "사전 배포된 가중치가 없는"):
                module.MlRestoreProvider.from_pretrained(techniques=("palatalize",))
        download.assert_not_called()

    def test_cached_file_of_matching_size_is_not_redownloaded(self) -> None:
        # Given — 캐시에 선언된 크기와 같은 파일이 이미 있다
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            entry = module.PRETRAINED_MANIFEST["tensify"]
            (root / entry["onnx_file"]).write_bytes(b"x" * entry["onnx_bytes"])
            (root / entry["vocab_file"]).write_bytes(_padded_vocab(entry["vocab_bytes"]))
            # When
            with mock.patch.object(module, "_download_file") as download:
                module.MlRestoreProvider.from_pretrained(
                    techniques=("tensify",), cache_dir=root
                )
            # Then
            download.assert_not_called()

    def test_force_download_refetches_even_when_cached(self) -> None:
        # Given
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            entry = module.PRETRAINED_MANIFEST["tensify"]

            def fake_download(url, dest, *, sha256, size):
                dest.write_text(json.dumps({PAD_CHAR: PAD_ID}), encoding="utf-8")

            (root / entry["onnx_file"]).write_bytes(b"x" * entry["onnx_bytes"])
            (root / entry["vocab_file"]).write_bytes(_padded_vocab(entry["vocab_bytes"]))
            # When
            with mock.patch.object(
                module, "_download_file", side_effect=fake_download
            ) as download:
                module.MlRestoreProvider.from_pretrained(
                    techniques=("tensify",), cache_dir=root, force_download=True
                )
            # Then — onnx와 vocab 두 파일 모두 다시 받는다
            self.assertEqual(download.call_count, 2)

    def test_download_url_points_at_the_pinned_release_over_https(self) -> None:
        # Given
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            urls = []

            def fake_download(url, dest, *, sha256, size):
                urls.append(url)
                dest.write_text(json.dumps({PAD_CHAR: PAD_ID}), encoding="utf-8")

            # When
            with mock.patch.object(module, "_download_file", fake_download):
                module.MlRestoreProvider.from_pretrained(
                    techniques=("tensify",), cache_dir=root
                )
            # Then
            self.assertEqual(len(urls), 2)
            for url in urls:
                self.assertTrue(url.startswith("https://"))
                self.assertIn(module.PRETRAINED_REPO, url)
                self.assertIn(module.PRETRAINED_TAG, url)


if __name__ == "__main__":
    unittest.main()
