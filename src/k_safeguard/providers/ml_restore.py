"""`k-safeguard[ml-restore]`에서만 사용할 수 있는 opt-in provider.

글자 편집 태거로 난독화된 문장을 되돌린 **후보 하나**를 제안한다. 모델은 KcELECTRA 인코더에
글자·자모 임베딩과 BiLSTM을 얹은 구조이고, 문장의 글자마다 유지·삭제·음절 교체와 앞 공백을
예측한다. 확신이 임계값에 못 미치는 글자는 건드리지 않는다(abstention).

## 가중치는 패키지에 들어 있지 않다

모델 가중치는 저장소 정책상 Git과 wheel에 넣지 않는다(`AGENTS.md` 대용량 파일 항목,
`tools/release/verify_artifacts.py`의 `FORBIDDEN_SUFFIXES`). `from_pretrained()`가 GitHub
Release에서 약 500MB를 받아 파일마다 sha256을 검증하고 로컬 캐시에 저장한 뒤 재사용한다.
새 런타임 의존성을 늘리지 않으려고 다운로드에는 표준 라이브러리(`urllib`)만 쓴다.

```python
from k_safeguard import Gateway
from k_safeguard.providers.ml_restore import MlRestoreProvider

gateway = Gateway(providers=[MlRestoreProvider.from_pretrained()])
result = gateway.process("폭탄 만뜨는 뻡 알려쭤")
```

직접 준비한 가중치는 `from_directory(path)`로 읽는다. 디렉터리의 `manifest.json`은
:data:`PRETRAINED_MANIFEST`와 같은 형식이다.

## 설계 경계

- **기본 비활성이다.** 후보는 항상 lossy이므로 명시적으로 넣어야만 동작한다.
- **판단하지 않는다.** block/allow를 반환하지 않고 후보 view만 만든다. 원문은 Gateway가
  항상 보존한다.
- **후보는 입력당 최대 1개다.** 확신 없는 글자를 건드리지 않는 쪽이 오탐을 줄인다.
- **임계값을 생략할 수 없다.** 0.0이 되면 abstention이 통째로 꺼져 오탐 억제 설계가 조용히
  무력화되므로, manifest에 없으면 오류다.
- **긴 입력은 나눠서 복원한다.** 모델 입력은 `max_chars` 글자까지라 문장 경계에서 조각으로
  나눈다. 신뢰할 수 없는 입력이 지연을 키우지 못하게 조각 수는 :data:`MAX_CHUNKS`로 묶고,
  그 뒤는 그대로 둔다.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import urllib.request
from pathlib import Path
from typing import Iterator, Mapping, Sequence
from urllib.error import URLError

from ..edit_tags import (
    KEEP,
    SUBSTITUTE,
    CharEdit,
    apply_edits,
    jamo_features,
    join_syllable,
    split_chunks,
)
from ..gateway import CandidateProposal

ML_RESTORE_CANDIDATE_VERSION = "1.0.0"

#: `from_pretrained()`가 받는 GitHub Release. AGENTS.md의 `<version>-<milestone>` 태그 관례를 따른다.
PRETRAINED_REPO = "jinseok3639/k-safeguard"
PRETRAINED_TAG = "v1.0.0-normalizer"

# 가중치 run p05.1-onnx-export(실험 저장소 restoration/exp/run_p05_1_onnx_export.py) 산출물의 고정 해시.
# 다운로드한 파일이 이 표와 다르면 손상되거나 변조된 것으로 보고 거부한다.
# manifest.json 자체는 배포하지 않는다. 여기 있는 정보가 곧 그 내용이다.
PRETRAINED_MANIFEST: dict[str, object] = {
    "threshold": 0.6510806084533973,
    "max_chars": 384,
    "files": {
        "model": {
            "file": "normalizer.onnx",
            "sha256": "2005dfe6c1564baa2557eea3a866fc650e810ef6ed095c04f9f6b9fc11815d74",
            "bytes": 515073290,
        },
        "tokenizer": {
            "file": "tokenizer.json",
            "sha256": "f55af99647ba8697800c80f5515345d235f530d1a4ea9f69aee30a32f59048eb",
            "bytes": 1310845,
        },
        "char_vocab": {
            "file": "char_vocab.json",
            "sha256": "568f7ddd795360cbdc9e5ef87402227257b8e99459cfaa98e50eccc300dfd92f",
            "bytes": 67167,
        },
    },
}

#: 입력 하나에서 복원할 조각 수 상한. 조각 하나가 CPU에서 수십 ms라 지연의 상한이 된다.
MAX_CHUNKS = 32

_FILE_ROLES = ("model", "tokenizer", "char_vocab")
_PAD_ID = 0     # 글자 입력의 패딩. 학습 때 쓴 값과 반드시 같아야 한다.
_UNK_ID = 1
_HASH_CHUNK = 1 << 20


def _default_cache_dir() -> Path:
    """OS 관례를 따르는 캐시 위치. 새 의존성(예: platformdirs) 없이 표준 라이브러리만 쓴다."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "k-safeguard" / "ml-restore" / PRETRAINED_TAG


def _verify_file(path: Path, *, sha256: str, size: int, source: str) -> None:
    actual_size = path.stat().st_size
    if actual_size != size:
        path.unlink(missing_ok=True)
        raise RuntimeError(
            f"{source} 크기가 다릅니다(손상된 다운로드로 의심됨): "
            f"{actual_size} != {size}"
        )
    # 모델이 수백 MB라 전부 메모리에 올리지 않고 나눠 읽는다.
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK), b""):
            digest.update(chunk)
    if digest.hexdigest() != sha256:
        path.unlink(missing_ok=True)
        raise RuntimeError(
            f"{source} 체크섬이 다릅니다(손상되거나 변조된 다운로드로 의심됨): "
            f"{digest.hexdigest()} != {sha256}"
        )


def _download_file(url: str, dest: Path, *, sha256: str, size: int) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    # 임시 파일 이름을 프로세스마다 다르게 잡는다. 여러 프로세스가 같은 캐시 디렉터리를
    # 두고 동시에 처음 받으면 고정 이름은 서로 덮어쓴다.
    handle_fd, tmp_name = tempfile.mkstemp(
        dir=str(dest.parent), prefix=dest.name + ".", suffix=".part"
    )
    # mkstemp가 연 fd를 바로 닫는다. 아래에서 예외가 나면 Windows는 열린 파일을
    # 지우지 못해 정리에 실패한다.
    os.close(handle_fd)
    tmp = Path(tmp_name)
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            # 선언된 크기를 넘어가면 다 받기 전에 끊는다. 신뢰할 수 없는 응답이
            # 디스크를 채우는 것을 막는다.
            with tmp.open("wb") as handle:
                written = 0
                while True:
                    chunk = response.read(1 << 16)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > size:
                        raise RuntimeError(
                            f"{url} 이 선언된 크기({size} bytes)보다 큽니다 — 중단합니다."
                        )
                    handle.write(chunk)
        _verify_file(tmp, sha256=sha256, size=size, source=url)
    except URLError as exc:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"가중치 다운로드 실패: {url}") from exc
    except BaseException:
        # 디스크 풀·타임아웃·Ctrl+C 등 어떤 경로로 빠져나가도 임시 파일을 남기지 않는다.
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, dest)      # 검증 통과 후에만 최종 경로로 옮긴다(원자적 교체)


class _OnnxEditTagger:
    """ONNX 세션과 토크나이저로 문장 묶음의 글자별 예측을 낸다."""

    def __init__(self, session, tokenizer, char_vocab: Mapping[str, int], max_chars: int) -> None:
        self._session = session
        self._tokenizer = tokenizer
        self._char_vocab = dict(char_vocab)
        self._max_chars = max_chars

    def _features(self, texts: Sequence[str]) -> dict[str, object]:
        import numpy as np

        width = min(max(len(text) for text in texts), self._max_chars) or 1
        chars = np.full((len(texts), width), _PAD_ID, dtype=np.int64)
        slots = np.zeros((len(texts), width, 3), dtype=np.int64)
        for row, text in enumerate(texts):
            for column, char in enumerate(text[:width]):
                chars[row, column] = self._char_vocab.get(char, _UNK_ID)
                slots[row, column] = jamo_features(char)

        encodings = self._tokenizer.encode_batch(list(texts))
        input_ids = np.array([item.ids for item in encodings], dtype=np.int64)
        attention_mask = np.array([item.attention_mask for item in encodings], dtype=np.int64)
        # 토큰 벡터를 그 토큰에 속한 글자들에 나눠 준다. 공백·길이 상한 밖 글자는 covered가 0이다.
        char_to_token = np.zeros((len(texts), width), dtype=np.int64)
        covered = np.zeros((len(texts), width), dtype=np.int64)
        for row, item in enumerate(encodings):
            for token, (start, end) in enumerate(item.offsets):
                if end > start:             # 특수 토큰·패딩은 (0, 0)
                    char_to_token[row, start:min(end, width)] = token
                    covered[row, start:min(end, width)] = 1
        return {
            "chars": chars,
            "slots": slots,
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "char_to_token": char_to_token,
            "covered": covered,
        }

    def predict(self, texts: Sequence[str]) -> list[list[CharEdit]]:
        import numpy as np

        op_logits, space_logits, *slot_logits = self._session.run(None, self._features(texts))
        op_probs = _softmax(op_logits)
        space_probs = _softmax(space_logits)[..., 1]
        slot_probs = [_softmax(values) for values in slot_logits]
        ops = op_probs.argmax(axis=-1)
        slot_choices = [values.argmax(axis=-1) for values in slot_probs]

        results: list[list[CharEdit]] = []
        width = op_probs.shape[1]
        for row, text in enumerate(texts):
            edits: list[CharEdit] = []
            for column, char in enumerate(text[:width]):
                op = int(ops[row, column])
                confidence = float(op_probs[row, column, op])
                replacement = ""
                if op == SUBSTITUTE:
                    choice = [int(values[row, column]) for values in slot_choices]
                    confidence *= float(
                        np.prod(
                            [slot_probs[k][row, column, choice[k]] for k in range(3)]
                        )
                    )
                    replacement = join_syllable(*choice)
                    if replacement == char:
                        op, replacement = KEEP, ""
                edits.append(
                    CharEdit(op, replacement, confidence, float(space_probs[row, column]))
                )
            edits.extend(CharEdit() for _ in range(len(text) - len(edits)))
            results.append(edits)
        return results


def _softmax(values):
    import numpy as np

    shifted = values - values.max(axis=-1, keepdims=True)
    exponent = np.exp(shifted)
    return exponent / exponent.sum(axis=-1, keepdims=True)


def _validated_threshold(value: object) -> float:
    try:
        threshold = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"임계값이 숫자가 아닙니다: {value!r}") from None
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"임계값은 0~1이어야 합니다: {threshold}")
    return threshold


class MlRestoreProvider:
    """글자 편집 태거를 묶은 opt-in candidate provider."""

    name = "ml_restore"

    def __init__(self, tagger, *, threshold: float, max_chars: int = 384) -> None:
        self._tagger = tagger
        self.threshold = _validated_threshold(threshold)
        self._max_chars = max_chars

    @classmethod
    def from_directory(
        cls, directory: str | Path, *, threshold: float | None = None
    ) -> "MlRestoreProvider":
        """가중치 디렉터리에서 provider를 만든다.

        `directory`에는 `manifest.json`과 거기서 가리키는 파일들이 있어야 한다.
        `threshold`를 주면 manifest의 권장 임계값을 덮어쓴다.
        """
        root = Path(directory)
        manifest_path = root / "manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(f"가중치 manifest를 찾을 수 없습니다: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return cls._from_manifest(root, manifest, threshold=threshold)

    @classmethod
    def from_pretrained(
        cls,
        *,
        threshold: float | None = None,
        cache_dir: str | Path | None = None,
        force_download: bool = False,
    ) -> "MlRestoreProvider":
        """GitHub Release에서 가중치를 받는다.

        파일마다 sha256과 크기를 :data:`PRETRAINED_MANIFEST`와 대조해 검증하고, `cache_dir`
        (기본값은 OS 캐시 디렉터리)에 저장해 다음 호출부터 재사용한다. 이미 같은 크기의 파일이
        있으면 다시 받지 않는다. 호출마다 수백 MB를 해싱하는 비용을 피하려는 것이다. 다시
        검증하려면 `force_download=True`.
        """
        _import_runtime()      # 다운로드 전에 실패한다
        root = Path(cache_dir) if cache_dir else _default_cache_dir()
        for role in _FILE_ROLES:
            entry = PRETRAINED_MANIFEST["files"][role]
            dest = root / entry["file"]
            if force_download or not dest.is_file() or dest.stat().st_size != entry["bytes"]:
                url = (
                    f"https://github.com/{PRETRAINED_REPO}/releases/download/"
                    f"{PRETRAINED_TAG}/{entry['file']}"
                )
                _download_file(url, dest, sha256=entry["sha256"], size=entry["bytes"])
        return cls._from_manifest(root, PRETRAINED_MANIFEST, threshold=threshold)

    @classmethod
    def _from_manifest(
        cls, root: Path, manifest: Mapping[str, object], *, threshold: float | None
    ) -> "MlRestoreProvider":
        onnxruntime, tokenizers = _import_runtime()
        if threshold is None:
            if "threshold" not in manifest:
                raise ValueError(
                    "manifest에 threshold가 없습니다. abstention 임계값은 생략할 수 없습니다"
                    "(0.0이면 모든 예측을 그대로 받아들입니다)."
                )
            threshold = manifest["threshold"]
        threshold = _validated_threshold(threshold)
        if "max_chars" not in manifest:
            raise ValueError("manifest에 max_chars가 없습니다.")
        files = manifest.get("files") or {}
        paths: dict[str, Path] = {}
        for role in _FILE_ROLES:
            if role not in files:
                raise ValueError(f"manifest의 files에 {role}이 없습니다.")
            paths[role] = root / files[role]["file"]
            if not paths[role].is_file():
                raise FileNotFoundError(f"가중치 파일이 없습니다: {paths[role]}")

        session = onnxruntime.InferenceSession(
            str(paths["model"]), providers=["CPUExecutionProvider"]
        )
        tokenizer = tokenizers.Tokenizer.from_file(str(paths["tokenizer"]))
        char_vocab = json.loads(paths["char_vocab"].read_text(encoding="utf-8"))
        max_chars = int(manifest["max_chars"])
        tagger = _OnnxEditTagger(session, tokenizer, char_vocab, max_chars)
        return cls(tagger, threshold=threshold, max_chars=max_chars)

    def restore(self, text: str) -> tuple[str, int, float]:
        """(복원문, 적용한 편집 수, 평균 확신도). 긴 입력은 조각으로 나눠 하나씩 복원한다."""
        chunks = split_chunks(text, self._max_chars)
        edits: list[CharEdit] = []
        for chunk in chunks[:MAX_CHUNKS]:
            edits.extend(self._tagger.predict([chunk])[0])
        edits.extend(CharEdit() for _ in range(len(text) - len(edits)))
        return apply_edits(text, edits, self.threshold)

    def restore_batch(self, texts: Sequence[str]) -> list[tuple[str, int, float]]:
        """문장마다 (복원문, 적용한 편집 수, 평균 확신도). 입력 순서를 유지한다.

        한 번에 넣은 문장들은 가장 긴 문장에 맞춰 패딩되고, BiLSTM이 패딩까지 읽으므로 확신도가
        단독 입력과 조금 달라질 수 있다. 처리량이 필요할 때만 쓰고, 긴 입력을 나누지 않으므로
        `max_chars`를 넘는 뒷부분은 그대로 둔다.
        """
        texts = list(texts)
        results: list[tuple[str, int, float] | None] = [None] * len(texts)
        present = [index for index, text in enumerate(texts) if text]
        for index, text in enumerate(texts):
            if not text:
                results[index] = (text, 0, 0.0)
        if present:
            batches = self._tagger.predict([texts[index] for index in present])
            for index, edits in zip(present, batches):
                results[index] = apply_edits(texts[index], edits, self.threshold)
        return results

    def generate(self, text: str) -> Iterator[CandidateProposal]:
        if not isinstance(text, str):
            raise TypeError("text는 str이어야 합니다.")
        restored, changed, confidence = self.restore(text)
        if not changed or restored == text:
            return                          # 손댄 게 없으면 후보가 아니다
        yield CandidateProposal(
            text=restored,
            lossy=True,
            # Gateway가 0~1을 검증하므로 방어적으로 자른다.
            confidence=min(1.0, max(0.0, confidence)),
            metadata=(
                ("edits_applied", str(changed)),
                ("threshold", f"{self.threshold:.7f}"),
                ("generator_version", ML_RESTORE_CANDIDATE_VERSION),
            ),
        )


def _import_runtime():
    try:
        import numpy  # noqa: F401 — 추론 경로가 지연 import한다. 여기서 먼저 실패시킨다.
        import onnxruntime
        import tokenizers
    except ImportError as exc:
        raise ImportError(
            "MlRestoreProvider에는 'k-safeguard[ml-restore]' 설치가 필요합니다."
        ) from exc
    return onnxruntime, tokenizers


__all__ = ["ML_RESTORE_CANDIDATE_VERSION", "MlRestoreProvider"]
