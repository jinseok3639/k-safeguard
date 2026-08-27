"""`k-safeguard[ml-restore]`에서만 사용할 수 있는 실험적 provider.

자모 슬롯 위치별 분류기로 난독화된 표기를 되돌린 **후보 하나**를 제안한다.
:class:`~k_safeguard.providers.tensify.TensifyInverseProvider`가 가능한 되돌림
조합을 전부 나열하는 것과 달리, 이쪽은 자리마다 "무엇으로 되돌릴지"를 실제로
판단하고 확신이 없는 자리는 건드리지 않는다(abstention).

## 가중치는 패키지에 들어 있지 않다

`ChosungLexiconProvider`가 어휘 사전을 싣지 않고 호출자가 만든 사전을 받는 것과
같은 구조다. 모델 가중치는 저장소 정책상 Git과 wheel에 넣지 않으므로
(`AGENTS.md` 대용량 파일 항목, `tools/release/verify_artifacts.py`의
`FORBIDDEN_SUFFIXES`), 호출자가 가중치 디렉터리 경로를 준다.

가중치 디렉터리는 `manifest.json` 하나로 자기기술적이어야 하며, 기법마다
`<technique>.onnx`와 `<technique>.vocab.json`을 갖는다. 재생성 방법은 manifest의
`provenance.regenerate_with` 필드에 기록돼 있다.

```python
from k_safeguard import Gateway
from k_safeguard.providers.ml_restore import MlRestoreProvider

provider = MlRestoreProvider.from_directory("path/to/weights")
gateway = Gateway(providers=[provider])
result = gateway.process("폭탄 만뜨는 뻡 알려쭤")
```

가중치를 직접 준비할 필요가 없으면 `from_pretrained()`로 GitHub Release에 올려둔
가중치를 받는다. 파일마다 sha256을 검증하고 로컬 캐시에 저장한 뒤 재사용한다 —
새 런타임 의존성을 늘리지 않으려고 표준 라이브러리(`urllib`)만 쓴다.

```python
provider = MlRestoreProvider.from_pretrained()
```

## 설계 경계

- **기본 비활성이다.** 승격 기준(`dev_note/EVALUATION_SPEC.md` §11.4)의 clean benign
  Mutation Rate ≤1%를 아직 통과하지 못한다. 명시적으로 넣어야만 동작한다.
- **판단하지 않는다.** block/allow를 반환하지 않고 후보 view만 만든다. 원문은
  Gateway가 항상 보존한다.
- **후보는 기법당 최대 1개다.** 확신 없는 자리를 건드리지 않는 쪽이 오탐을 줄인다는
  것이 실험 결론이므로, 여러 대안을 뿌리는 대신 하나만 낸다.
- **임계값은 기법마다 다르다.** 모델별 확률 보정이 다르고, confidence를 담당 슬롯 수만큼
  곱하기 때문이다(`liaison`은 초성·종성 2개라 값이 구조적으로 작다). 전역 단일 임계값은
  쓸 수 없고, manifest에 기법마다 반드시 있어야 한다 — 생략하면 오류다.
- **입력 길이에 상한이 있다.** `liaison`·`jongseong_cram`은 모든 음절을 후보로 잡으므로
  긴 입력에서 배치가 그대로 커진다. `MAX_CANDIDATE_SITES`를 넘으면 복원하지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import urllib.request
from pathlib import Path
from typing import Iterator, Mapping
from urllib.error import URLError

from ..gateway import CandidateProposal
from ..jamo_slots import (
    CharVocab,
    encode_sites,
    extract_sites,
    join_syllable,
    unknown_slots,
)

ML_RESTORE_CANDIDATE_VERSION = "0.1.0"

#: 후보 생성 순서. Gateway가 `max_views`에서 뒤쪽을 자르므로 순서가 곧 우선순위다.
#: 후보 위치 규칙이 좁은(= 정상 문장을 덜 건드리는) 기법을 먼저 낸다.
DEFAULT_ORDER = ("tensify", "liaison", "jongseong_cram")

#: `from_pretrained()`가 받는 GitHub Release. AGENTS.md의 `<version>-<milestone>`
#: 태그 관례를 따른다.
PRETRAINED_REPO = "jinseok3639/k-safeguard"
PRETRAINED_TAG = "v0.2.0-ml-restore"

#: 한 번에 방문할 후보 자리 상한. `liaison`·`jongseong_cram`은 모든 음절을 후보로 잡으므로
#: 긴 입력이 들어오면 배치가 그대로 커진다. 가드레일 앞단은 신뢰할 수 없는 입력을 받는
#: 자리이므로, 상한을 넘으면 복원을 시도하지 않고 조용히 물러난다(원문은 Gateway가 보존).
MAX_CANDIDATE_SITES = 4096

# 가중치 run proto-20260826b(ML 샌드박스 exp/run_proto_export.py) 산출물의 고정 해시.
# 다운로드한 파일이 이 표와 다르면 손상되거나 변조된 것으로 보고 거부한다.
# manifest.json 자체는 배포하지 않는다 — 여기 있는 정보가 곧 그 내용이다.
PRETRAINED_MANIFEST: dict[str, dict[str, object]] = {
    "tensify": {
        "threshold": 0.999999,
        "window": 4,
        "onnx_file": "tensify.onnx",
        "onnx_sha256": "af5a8a71f8a006d7edabf07b8e80c593073361a68e85e60db42b551eb7d14069",
        "onnx_bytes": 1318470,
        "vocab_file": "tensify.vocab.json",
        "vocab_sha256": "471d8461a6c2be99741cace037c9fc5609f5a693cdbc808f650f9b23202c255e",
        "vocab_bytes": 38989,
    },
    "liaison": {
        "threshold": 0.99,
        "window": 4,
        "onnx_file": "liaison.onnx",
        "onnx_sha256": "ee6f5c4ff48acf8c7a3bf0096eee3b820f1be2264774368a92376e94ab2556d0",
        "onnx_bytes": 1324260,
        "vocab_file": "liaison.vocab.json",
        "vocab_sha256": "cbf48e5171c6408859eefcb37cd3220e92a6c9a36495c098a118351d152454d7",
        "vocab_bytes": 37288,
    },
    "jongseong_cram": {
        "threshold": 0.99,
        "window": 4,
        "onnx_file": "jongseong_cram.onnx",
        "onnx_sha256": "344683d2a251463dd83bf5755526ecdde63af9d79e997b693fb77e241361cfa9",
        "onnx_bytes": 1441771,
        "vocab_file": "jongseong_cram.vocab.json",
        "vocab_sha256": "f7ca77f8c8829c928f67a033ea89c8b213fc499ded00b74022b63083ff635445",
        "vocab_bytes": 47298,
    },
}


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
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != sha256:
        path.unlink(missing_ok=True)
        raise RuntimeError(
            f"{source} 체크섬이 다릅니다(손상되거나 변조된 다운로드로 의심됨): "
            f"{digest} != {sha256}"
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


class _Restorer:
    """기법 하나의 ONNX 세션과 그 인코딩 설정."""

    def __init__(
        self,
        technique: str,
        session,
        vocab: CharVocab,
        window: int,
        threshold: float,
    ) -> None:
        self.technique = technique
        self.session = session
        self.vocab = vocab
        self.window = window
        self.threshold = threshold
        self.slots = unknown_slots(technique)
        outputs = len(session.get_outputs())
        if outputs < len(self.slots):
            raise ValueError(
                f"{technique} 모델의 출력이 부족합니다: {outputs}개 "
                f"(담당 슬롯 {len(self.slots)}개). 가중치와 기법이 어긋난 것 같습니다."
            )

    def restore(self, text: str) -> tuple[str, int, float]:
        """(복원문, 바꾼 자리 수, 바꾼 자리 평균 confidence).

        임계값을 넘지 못한 자리는 입력을 그대로 둔다 — 이 자리별 abstention이
        오탐을 1% 아래로 누르는 유일한 수단이라는 것이 실험 결론이다.
        """
        import numpy as np

        sites = extract_sites(text, self.technique, self.window)
        if not sites or len(sites) > MAX_CANDIDATE_SITES:
            # 후보가 없거나 너무 많으면 손대지 않는다. 상한을 넘는 입력에 대해 부분만
            # 복원하면 어디까지 다뤘는지 알 수 없는 view가 나가므로 전부 포기한다.
            return text, 0, 0.0

        chars, positions, slots = encode_sites(sites, self.vocab)
        logits = self.session.run(
            None, {"chars": chars, "pos": positions, "slots": slots}
        )

        # 슬롯별 softmax -> argmax와 그 확률. 출력 순서는 export 때 고정한 슬롯 순서다.
        predicted: dict[int, "np.ndarray"] = {}
        probability: dict[int, "np.ndarray"] = {}
        for index, slot in enumerate(self.slots):
            values = logits[index]
            values = values - values.max(axis=1, keepdims=True)
            exponent = np.exp(values)
            probabilities = exponent / exponent.sum(axis=1, keepdims=True)
            choice = probabilities.argmax(axis=1)
            predicted[slot] = choice
            probability[slot] = probabilities[np.arange(len(choice)), choice]

        output = list(text)
        confidences: list[float] = []
        for row, site in enumerate(sites):
            confidence = 1.0
            for slot in self.slots:
                confidence *= float(probability[slot][row])
            if confidence < self.threshold:
                continue                    # abstention — 이 자리는 원문 그대로 둔다
            cho, jung, jong = site.input_slots
            if 0 in self.slots:
                cho = int(predicted[0][row])
            if 1 in self.slots:
                jung = int(predicted[1][row])
            if 2 in self.slots:
                jong = int(predicted[2][row])
            if min(cho, jung, jong) < 0:
                continue                    # 슬롯을 다 못 채우면 손대지 않는다
            output[site.char_index] = join_syllable(cho, jung, jong)
            confidences.append(confidence)

        restored = "".join(output)
        if restored == text or not confidences:
            return text, 0, 0.0
        return restored, len(confidences), sum(confidences) / len(confidences)


class MlRestoreProvider:
    """자모 슬롯 복원 모델을 묶은 opt-in candidate provider."""

    name = "ml_restore"

    def __init__(
        self,
        restorers: Mapping[str, object],
        *,
        order: tuple[str, ...] = DEFAULT_ORDER,
    ) -> None:
        if not restorers:
            raise ValueError("복원기가 최소 하나는 있어야 합니다.")
        self._restorers = dict(restorers)
        known = [technique for technique in order if technique in self._restorers]
        self._order = tuple(known) + tuple(sorted(set(self._restorers) - set(known)))

    @classmethod
    def from_directory(
        cls,
        directory: str | Path,
        *,
        techniques: tuple[str, ...] | None = None,
        thresholds: Mapping[str, float] | None = None,
    ) -> "MlRestoreProvider":
        """가중치 디렉터리에서 provider를 만든다.

        `directory`에는 `manifest.json`과 기법별 `.onnx`·`.vocab.json`이 있어야 한다.
        `thresholds`를 주면 manifest의 권장 임계값을 덮어쓴다. 가중치를 직접
        준비하지 않았다면 `from_pretrained()`를 쓴다.
        """
        root = Path(directory)
        manifest_path = root / "manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(f"가중치 manifest를 찾을 수 없습니다: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = manifest.get("techniques") or {}
        if not entries:
            raise ValueError(f"manifest에 기법이 없습니다: {manifest_path}")
        return cls._from_entries(
            root, entries, techniques=techniques, thresholds=thresholds
        )

    @classmethod
    def from_pretrained(
        cls,
        *,
        techniques: tuple[str, ...] | None = None,
        thresholds: Mapping[str, float] | None = None,
        cache_dir: str | Path | None = None,
        force_download: bool = False,
    ) -> "MlRestoreProvider":
        """GitHub Release(`{PRETRAINED_REPO}` `{PRETRAINED_TAG}`)에서 가중치를 받는다.

        파일마다 sha256과 크기를 :data:`PRETRAINED_MANIFEST`와 대조해 검증하고,
        `cache_dir`(기본값은 OS 캐시 디렉터리)에 저장해 다음 호출부터 재사용한다.
        이미 같은 크기의 파일이 있으면 다시 받지 않는다 — 매 호출마다 몇 MB를
        해싱하는 비용을 피하려는 것이다. 다시 검증하려면 `force_download=True`.
        """
        try:
            import onnxruntime  # noqa: F401 — from_directory와 같은 에러 메시지로 조기 실패
        except ImportError as exc:
            raise ImportError(
                "MlRestoreProvider에는 'k-safeguard[ml-restore]' 설치가 필요합니다."
            ) from exc

        root = Path(cache_dir) if cache_dir else _default_cache_dir()
        selected = tuple(techniques) if techniques else tuple(PRETRAINED_MANIFEST)
        for technique in selected:
            entry = PRETRAINED_MANIFEST.get(technique)
            if entry is None:
                raise ValueError(
                    f"사전 배포된 가중치가 없는 기법입니다: {technique!r} "
                    f"(사용 가능: {', '.join(sorted(PRETRAINED_MANIFEST))})"
                )
            for kind in ("onnx", "vocab"):
                filename = entry[f"{kind}_file"]
                dest = root / filename
                size = entry[f"{kind}_bytes"]
                if force_download or not dest.is_file() or dest.stat().st_size != size:
                    url = f"https://github.com/{PRETRAINED_REPO}/releases/download/{PRETRAINED_TAG}/{filename}"
                    _download_file(url, dest, sha256=entry[f"{kind}_sha256"], size=size)
        return cls._from_entries(
            root, PRETRAINED_MANIFEST, techniques=techniques, thresholds=thresholds
        )

    @classmethod
    def _from_entries(
        cls,
        root: Path,
        entries: Mapping[str, Mapping[str, object]],
        *,
        techniques: tuple[str, ...] | None,
        thresholds: Mapping[str, float] | None,
    ) -> "MlRestoreProvider":
        try:
            import onnxruntime
        except ImportError as exc:
            raise ImportError(
                "MlRestoreProvider에는 'k-safeguard[ml-restore]' 설치가 필요합니다."
            ) from exc

        selected = tuple(techniques) if techniques else tuple(entries)
        if not selected:
            raise ValueError("기법이 없습니다.")

        restorers: dict[str, _Restorer] = {}
        for technique in selected:
            entry = entries.get(technique)
            if entry is None:
                raise ValueError(
                    f"가중치에 없는 기법입니다: {technique!r} "
                    f"(사용 가능: {', '.join(sorted(entries))})"
                )
            override = (thresholds or {}).get(technique)
            if override is None:
                # 기본값을 두지 않는다. 키가 빠지면 threshold 0.0이 되어 abstention이
                # 통째로 꺼지는데, 그건 이 provider의 오탐 억제 설계 전부를 조용히
                # 무력화한다 — 조용히 넘어가는 대신 여기서 멈춘다.
                if "threshold" not in entry:
                    raise ValueError(
                        f"{technique}에 threshold가 없습니다. abstention 임계값은 "
                        f"생략할 수 없습니다(0.0이면 모든 예측을 그대로 받아들입니다)."
                    )
                override = entry["threshold"]
            try:
                threshold = float(override)
            except (TypeError, ValueError):
                raise ValueError(
                    f"{technique}의 임계값이 숫자가 아닙니다: {override!r}"
                ) from None
            if not 0.0 <= threshold <= 1.0:
                raise ValueError(f"{technique}의 임계값은 0~1이어야 합니다: {threshold}")

            onnx_path = root / entry["onnx_file"]
            vocab_path = root / entry["vocab_file"]
            for path in (onnx_path, vocab_path):
                if not path.is_file():
                    raise FileNotFoundError(f"가중치 파일이 없습니다: {path}")

            session = onnxruntime.InferenceSession(
                str(onnx_path), providers=["CPUExecutionProvider"]
            )
            vocab = CharVocab(json.loads(vocab_path.read_text(encoding="utf-8")))
            restorers[technique] = _Restorer(
                technique, session, vocab, int(entry["window"]), threshold
            )
        return cls(restorers)

    def generate(self, text: str) -> Iterator[CandidateProposal]:
        if not isinstance(text, str):
            raise TypeError("text는 str이어야 합니다.")
        for technique in self._order:
            restorer = self._restorers[technique]
            restored, changed, confidence = restorer.restore(text)
            if not changed or restored == text:
                continue                    # 손댄 게 없으면 후보가 아니다
            yield CandidateProposal(
                text=restored,
                lossy=True,
                # Gateway가 0~1을 검증하므로 방어적으로 자른다.
                confidence=min(1.0, max(0.0, confidence)),
                metadata=(
                    ("technique", technique),
                    ("slots_changed", str(changed)),
                    ("threshold", f"{restorer.threshold:.7f}"),
                    ("generator_version", ML_RESTORE_CANDIDATE_VERSION),
                ),
            )


__all__ = ["ML_RESTORE_CANDIDATE_VERSION", "MlRestoreProvider"]
