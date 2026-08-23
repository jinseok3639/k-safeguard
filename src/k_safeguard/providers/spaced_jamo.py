"""공백으로 분리된 한글 자모를 위한 bounded opt-in 후보 provider."""

from __future__ import annotations

import re
from typing import Iterator

from ..gateway import CandidateProposal
from ..normalization import normalize_korean


SPACED_JAMO_CANDIDATE_VERSION = "0.1.0"
_JAMO_CLASS = "\u1100-\u11ff\u3130-\u318f"
_JAMO_RE = re.compile(f"[{_JAMO_CLASS}]")
_HANGUL_SYLLABLE_RE = re.compile("[\uac00-\ud7a3]")


class SpacedJamoProvider:
    """ASCII 공백으로 띄어 쓴 자모열을 완성형 한글 후보로 복원한다.

    공백 삭제는 의미를 바꿀 수 있으므로 기본 Gateway에는 연결되지 않는다. 한
    자모열이 완성형 음절로 전부 조합될 때만 후보를 만들며, 원문 view는 Gateway가
    별도로 보존한다.
    """

    name = "spaced_jamo"

    def __init__(
        self,
        *,
        min_jamo: int = 4,
        max_jamo_per_span: int = 64,
        max_spans: int = 8,
    ) -> None:
        if min_jamo < 2:
            raise ValueError("min_jamo는 2 이상이어야 합니다.")
        if max_jamo_per_span < min_jamo:
            raise ValueError("max_jamo_per_span은 min_jamo 이상이어야 합니다.")
        if max_spans < 1:
            raise ValueError("max_spans는 1 이상이어야 합니다.")

        self._min_jamo = min_jamo
        self._max_jamo_per_span = max_jamo_per_span
        self._max_spans = max_spans
        self._span_re = re.compile(
            f"[{_JAMO_CLASS}](?: +[{_JAMO_CLASS}])"
            f"{{{min_jamo - 1},}}"
        )

    def generate(self, text: str) -> Iterator[CandidateProposal]:
        if not isinstance(text, str):
            raise TypeError("text는 str이어야 합니다.")

        output: list[str] = []
        source_ranges: list[str] = []
        total_jamo = 0
        cursor = 0

        for match in self._span_re.finditer(text):
            if len(source_ranges) >= self._max_spans:
                break

            source = match.group(0)
            jamo_count = len(_JAMO_RE.findall(source))
            if jamo_count > self._max_jamo_per_span:
                continue

            collapsed = source.replace(" ", "")
            restored = normalize_korean(collapsed).text
            if (
                restored == collapsed
                or _JAMO_RE.search(restored) is not None
                or _HANGUL_SYLLABLE_RE.search(restored) is None
            ):
                continue

            output.append(text[cursor:match.start()])
            output.append(restored)
            cursor = match.end()
            source_ranges.append(f"{match.start()}:{match.end()}")
            total_jamo += jamo_count

        if not source_ranges:
            return

        output.append(text[cursor:])
        yield CandidateProposal(
            text="".join(output),
            lossy=True,
            confidence=None,
            metadata=(
                ("restored_spans", str(len(source_ranges))),
                ("restored_jamo", str(total_jamo)),
                ("source_ranges", ",".join(source_ranges)),
                ("min_jamo", str(self._min_jamo)),
                ("max_jamo_per_span", str(self._max_jamo_per_span)),
                ("max_spans", str(self._max_spans)),
                ("generator_version", SPACED_JAMO_CANDIDATE_VERSION),
            ),
        )


__all__ = ["SPACED_JAMO_CANDIDATE_VERSION", "SpacedJamoProvider"]
