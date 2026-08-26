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

## 설계 경계

- **기본 비활성이다.** 승격 기준(`dev_note/EVALUATION_SPEC.md` §11.4)의 clean benign
  Mutation Rate ≤1%를 아직 통과하지 못한다. 명시적으로 넣어야만 동작한다.
- **판단하지 않는다.** block/allow를 반환하지 않고 후보 view만 만든다. 원문은
  Gateway가 항상 보존한다.
- **후보는 기법당 최대 1개다.** 확신 없는 자리를 건드리지 않는 쪽이 오탐을 줄인다는
  것이 실험 결론이므로, 여러 대안을 뿌리는 대신 하나만 낸다.
- **임계값은 기법마다 다르다.** 모델별 확률 보정이 달라 전역 단일 임계값은 쓸 수 없다.
  manifest의 권장값을 기본으로 쓴다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, Mapping

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
        self._outputs = [output.name for output in session.get_outputs()]

    def restore(self, text: str) -> tuple[str, int, float]:
        """(복원문, 바꾼 자리 수, 바꾼 자리 평균 confidence).

        임계값을 넘지 못한 자리는 입력을 그대로 둔다 — 이 자리별 abstention이
        오탐을 1% 아래로 누르는 유일한 수단이라는 것이 실험 결론이다.
        """
        import numpy as np

        sites = extract_sites(text, self.technique, self.window)
        if not sites:
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
        `thresholds`를 주면 manifest의 권장 임계값을 덮어쓴다.
        """
        try:
            import onnxruntime
        except ImportError as exc:
            raise ImportError(
                "MlRestoreProvider에는 'k-safeguard[ml-restore]' 설치가 필요합니다."
            ) from exc

        root = Path(directory)
        manifest_path = root / "manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(f"가중치 manifest를 찾을 수 없습니다: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        entries = manifest.get("techniques") or {}
        selected = tuple(techniques) if techniques else tuple(entries)
        if not selected:
            raise ValueError(f"manifest에 기법이 없습니다: {manifest_path}")

        restorers: dict[str, _Restorer] = {}
        for technique in selected:
            entry = entries.get(technique)
            if entry is None:
                raise ValueError(
                    f"manifest에 없는 기법입니다: {technique!r} "
                    f"(사용 가능: {', '.join(sorted(entries))})"
                )
            threshold = float(
                (thresholds or {}).get(technique, entry.get("threshold", 0.0))
            )
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
