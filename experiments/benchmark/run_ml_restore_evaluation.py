"""자모 슬롯 복원 provider의 문자열 수준 복원율과 정상 입력 비용을 진단한다.

`run_tensify_candidate_diagnostic.py`와 같은 층위다 — 가드레일 추론 없이 문자열만 본다.
다른 점은 그쪽이 후보 나열의 **oracle recall**(정답이 후보 안에 있는가)을 재는 반면,
여기서는 후보가 하나뿐이라 **그 하나가 맞는가**를 잰다.

`MlRestoreProvider`는 가중치를 패키지에 싣지 않으므로 `--weights`로 디렉터리를 받는다
(`run_clean_baseline.py`가 외부 모델 경로를 받는 것과 같다). 가중치 준비 방법은
[ML_RESTORE_CANDIDATES.md](./ML_RESTORE_CANDIDATES.md)에 있다.

`hf_repo/benchmark.jsonl`에는 `clean`과 `tensify`만 있다. provider가 가진 기법 중
benchmark에 해당 행이 없는 것(`liaison`, `jongseong_cram`)은 여기서 잴 수 없고,
그 수치는 별도 샌드박스 실험에 기록돼 있다.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable

DEFAULT_INPUT = Path("hf_repo/benchmark.jsonl")
DEFAULT_OUTPUT = Path("experiments/benchmark/baselines/ml_restore_v1.json")
SCHEMA_VERSION = "ml-restore-diagnostic-v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--weights",
        type=Path,
        required=True,
        help="manifest.json이 있는 가중치 디렉터리",
    )
    return parser.parse_args()


def char_error_rate(reference: str, hypothesis: str) -> float:
    """문자 단위 편집거리 / 참조 길이. 길이가 같으면 단순 불일치 비율과 같다."""
    if not reference:
        return 0.0 if not hypothesis else 1.0
    if len(reference) == len(hypothesis):
        return sum(a != b for a, b in zip(reference, hypothesis)) / len(reference)
    previous = list(range(len(hypothesis) + 1))
    for row, source in enumerate(reference, 1):
        current = [row]
        for column, target in enumerate(hypothesis, 1):
            current.append(
                min(
                    previous[column] + 1,
                    current[column - 1] + 1,
                    previous[column - 1] + (source != target),
                )
            )
        previous = current
    return previous[-1] / len(reference)


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{line_number}행은 JSON object여야 합니다.")
            rows.append(row)
    return rows


def observe_rows(
    rows: Iterable[dict[str, Any]],
    *,
    restore: Callable[[str], tuple[str, float | None]],
) -> list[dict[str, Any]]:
    """행마다 복원 결과와 그 효과를 관측한다.

    `restore`는 입력 문자열 하나를 받아 `(복원문, confidence)`를 돌려준다. 후보를 내지
    않으면 입력을 그대로, confidence는 `None`으로 돌려준다 — provider가 침묵한 경우다.
    """
    observations: list[dict[str, Any]] = []
    for row in rows:
        original = row["original"]
        text = row["text"]
        restored, confidence = restore(text)
        raw_cer = char_error_rate(original, text)
        residual_cer = char_error_rate(original, restored)
        observations.append(
            {
                "id": row.get("id"),
                "seed_id": row.get("seed_id"),
                "label": row.get("label"),
                "technique": row.get("technique"),
                "intensity": row.get("intensity"),
                "changed": text != original,
                "candidate_emitted": confidence is not None,
                "confidence": confidence,
                "mutated": restored != text,
                "exact": restored == original,
                "raw_cer": raw_cer,
                "residual_cer": residual_cer,
                "cer_reduction": raw_cer - residual_cer,
            }
        )
    return observations


def summarize_group(items: list[dict[str, Any]]) -> dict[str, Any]:
    changed = [item for item in items if item["changed"]]
    return {
        "n": len(items),
        "changed_n": len(changed),
        # provider가 후보를 낸 비율. 정상 입력에서는 낮을수록 좋다.
        "candidate_generation_rate": (
            sum(item["candidate_emitted"] for item in items) / len(items)
            if items
            else 0.0
        ),
        # 입력이 실제로 바뀐 비율. technique=clean에서는 이것이 오변경률이다.
        "mutation_rate": (
            sum(item["mutated"] for item in items) / len(items) if items else 0.0
        ),
        "exact_restoration_rate": (
            sum(item["exact"] for item in changed) / len(changed) if changed else None
        ),
        "mean_raw_cer": (
            statistics.fmean(item["raw_cer"] for item in changed) if changed else None
        ),
        "mean_residual_cer": (
            statistics.fmean(item["residual_cer"] for item in changed)
            if changed
            else None
        ),
        "mean_cer_reduction": (
            statistics.fmean(item["cer_reduction"] for item in changed)
            if changed
            else None
        ),
    }


def build_summary(observations: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for item in observations:
        groups[(item["technique"], item["intensity"], item["label"])].append(item)
    return {
        "overall": summarize_group(observations),
        "groups": [
            {
                "technique": technique,
                "intensity": intensity,
                "label": label,
                **summarize_group(items),
            }
            for (technique, intensity, label), items in sorted(
                groups.items(), key=lambda pair: tuple(str(key) for key in pair[0])
            )
        ],
    }


def main() -> None:
    from k_safeguard.providers.ml_restore import (
        ML_RESTORE_CANDIDATE_VERSION,
        MlRestoreProvider,
    )

    args = parse_args()
    provider = MlRestoreProvider.from_directory(args.weights)
    manifest = json.loads((args.weights / "manifest.json").read_text(encoding="utf-8"))
    rows = load_rows(args.input)

    # benchmark에 있는 기법 중 provider가 다룰 수 있는 것만 평가한다.
    available = set(provider._restorers)
    evaluated = sorted({row["technique"] for row in rows} & (available | {"clean"}))
    rows = [row for row in rows if row["technique"] in evaluated]

    def restore(text: str) -> tuple[str, float | None]:
        for proposal in provider.generate(text):
            return proposal.text, proposal.confidence
        return text, None

    observations = observe_rows(rows, restore=restore)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "input": str(args.input).replace("\\", "/"),
        "restorer": {
            "name": provider.name,
            "version": ML_RESTORE_CANDIDATE_VERSION,
            "weights_run_id": manifest.get("run_id"),
            "techniques": {
                technique: {
                    "threshold": entry["threshold"],
                    "unknown_slots": entry["unknown_slots"],
                    "window": entry["window"],
                }
                for technique, entry in sorted(manifest["techniques"].items())
            },
            "provenance": manifest.get("provenance", {}),
        },
        "scope": {
            "techniques": evaluated,
            "not_evaluated": sorted(available - set(evaluated)),
            "observations": len(observations),
        },
        "summary": build_summary(observations),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
