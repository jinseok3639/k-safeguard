"""한 어절 자모 공백화에 대한 SpacedJamoProvider 문자열 진단."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Iterable

from hf_repo.ko_obfuscator import jamo_decompose
from k_safeguard import Gateway
from k_safeguard.providers import SpacedJamoProvider


REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_ROOT = REPO_ROOT / "hf_repo" / "seeds"
_HANGUL_WORD_RE = re.compile("[\uac00-\ud7a3]+")


def load_seeds(seed_root: Path = SEED_ROOT) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for path in sorted(seed_root.glob("*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def space_one_word(
    text: str,
    *,
    min_jamo: int = 4,
    max_jamo: int = 64,
) -> str | None:
    """첫 bounded 한글 어절 하나만 자모 낱자 사이 ASCII 공백으로 바꾼다."""
    for match in _HANGUL_WORD_RE.finditer(text):
        decomposed = jamo_decompose(match.group(0), intensity=1.0, seed=0)
        if min_jamo <= len(decomposed) <= max_jamo:
            spaced = " ".join(decomposed)
            return text[: match.start()] + spaced + text[match.end() :]
    return None


def evaluate(seeds: Iterable[dict[str, object]]) -> dict[str, object]:
    provider = SpacedJamoProvider()
    gateway = Gateway(providers=[provider])
    default_gateway = Gateway()
    seed_count = 0
    eligible = 0
    provider_activated = 0
    exact_restored = 0
    default_changed = 0
    clean_activated = 0

    for seed in seeds:
        seed_count += 1
        original = str(seed["text"])
        clean_activated += int(len(gateway.process(original).views) > 1)
        variant = space_one_word(original)
        if variant is None:
            continue
        eligible += 1
        default_changed += int(default_gateway.process(variant).normalized != variant)
        candidates = [view.text for view in gateway.process(variant).views[1:]]
        provider_activated += int(bool(candidates))
        exact_restored += int(original in candidates)

    return {
        "seed_count": seed_count,
        "eligible_variants": eligible,
        "provider_activated": provider_activated,
        "exact_restored": exact_restored,
        "exact_restoration_rate": exact_restored / eligible if eligible else None,
        "default_gateway_changed": default_changed,
        "clean_provider_activated": clean_activated,
        "target_leakage": False,
    }


def seed_dataset_sha256(seed_root: Path = SEED_ROOT) -> str:
    digest = hashlib.sha256()
    for path in sorted(seed_root.glob("*.jsonl")):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def main() -> None:
    payload = {
        "schema_version": "spaced-jamo-diagnostic-v1",
        "dataset_sha256": seed_dataset_sha256(),
        "transform": "space_one_bounded_hangul_word",
        "metrics": evaluate(load_seeds()),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
