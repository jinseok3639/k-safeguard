"""O2/P3 손실성 변형의 bounded 역후보 exact-hit 진단.

후보 생성기는 variant text만 받고, original은 후보 생성이 끝난 뒤 exact-hit 계산에만
사용한다. 이 진단은 문자열 상한선이며 가드레일 차단율이나 의미 보존율이 아니다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from itertools import combinations, product
from pathlib import Path
from typing import Iterable, Iterator

from hf_repo.ko_obfuscator import (
    CRAMMED_FINALS,
    FINAL_NEAR_SOUND,
    JONG,
    _is_syllable,
    _join,
    _split,
)
from k_safeguard.providers import LiaisonInverseProvider


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = REPO_ROOT / "hf_repo" / "benchmark.jsonl"
TECHNIQUES = ("final_insertion", "final_near_sound", "liaison")


def final_insertion_candidates(text: str, limit: int) -> Iterator[str]:
    positions = [
        index
        for index, char in enumerate(text)
        if _is_syllable(char) and _split(char)[2] in CRAMMED_FINALS
    ]
    emitted = 0
    for replacement_count in range(len(positions), 0, -1):
        for selected in combinations(positions, replacement_count):
            output = list(text)
            for index in selected:
                initial, medial, _ = _split(output[index])
                output[index] = _join(initial, medial, 0)
            yield "".join(output)
            emitted += 1
            if emitted >= limit:
                return


def _near_sound_reverse_map() -> dict[str, tuple[str, ...]]:
    reverse: dict[str, list[str]] = {}
    for source, surface in FINAL_NEAR_SOUND.items():
        reverse.setdefault(surface, []).append(source)
    return {surface: tuple(sources) for surface, sources in reverse.items()}


_FINAL_NEAR_SOUND_REVERSE = _near_sound_reverse_map()


def final_near_sound_candidates(text: str, limit: int) -> Iterator[str]:
    positions: list[tuple[int, tuple[int, ...]]] = []
    for index, char in enumerate(text):
        if not _is_syllable(char):
            continue
        _, _, final = _split(char)
        sources = _FINAL_NEAR_SOUND_REVERSE.get(JONG[final])
        if sources:
            positions.append((index, tuple(JONG.index(source) for source in sources)))

    emitted = 0
    for replacement_count in range(1, len(positions) + 1):
        for selected in combinations(positions, replacement_count):
            for source_finals in product(*(options for _, options in selected)):
                output = list(text)
                for (index, _), source_final in zip(selected, source_finals):
                    initial, medial, _ = _split(output[index])
                    output[index] = _join(initial, medial, source_final)
                yield "".join(output)
                emitted += 1
                if emitted >= limit:
                    return


def liaison_candidates(text: str, limit: int) -> Iterator[str]:
    provider = LiaisonInverseProvider(max_candidates=limit)
    yield from (proposal.text for proposal in provider.generate(text))


GENERATORS = {
    "final_insertion": final_insertion_candidates,
    "final_near_sound": final_near_sound_candidates,
    "liaison": liaison_candidates,
}


def load_rows(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def evaluate(
    rows: Iterable[dict[str, object]],
    candidate_limits: Iterable[int],
) -> dict[str, object]:
    rows = list(rows)
    result: dict[str, object] = {}
    for technique in TECHNIQUES:
        changed = [
            row
            for row in rows
            if row["technique"] == technique and row["text"] != row["original"]
        ]
        by_limit: dict[str, object] = {}
        for limit in candidate_limits:
            if limit < 1:
                raise ValueError("candidate limit은 1 이상이어야 합니다.")
            generator = GENERATORS[technique]
            exact_hits = sum(
                str(row["original"])
                in set(generator(str(row["text"]), limit))
                for row in changed
            )
            by_limit[str(limit)] = {
                "exact_hits": exact_hits,
                "changed_rows": len(changed),
                "exact_hit_rate": exact_hits / len(changed) if changed else None,
            }
        result[technique] = {"by_candidate_limit": by_limit}
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--candidate-limit", type=int, action="append")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    limits = args.candidate_limit or [1, 3, 9, 32]
    payload = {
        "schema_version": "inverse-candidate-diagnostic-v1",
        "dataset_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "candidate_limits": limits,
        "target_leakage": False,
        "metrics": evaluate(load_rows(args.input), limits),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
