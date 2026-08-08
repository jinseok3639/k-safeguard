"""
build_benchmark.py — 시드 × 변환 × 강도의 데카르트 곱으로 벤치마크 파생.

시드(seeds/*.jsonl)만 사람/클로드가 늘리고, 난독화 변형은 여기서 결정론적으로 생성.
따라서 벤치마크 파일 자체는 커밋하지 않아도 됨(언제든 재현 가능).

사용: python3 build_benchmark.py > benchmark.jsonl
"""
import json
import glob
import hashlib
from ko_obfuscator import TRANSFORMS

INTENSITIES = [0.5, 1.0]        # 강도 축 (원하면 확장)
INCLUDE_CLEAN = True           # 원문(변형 없음) 대조군 포함


def load_seeds():
    for path in sorted(glob.glob("seeds/*.jsonl")):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)


def variant_id(seed_id, technique, intensity):
    key = f"{seed_id}|{technique}|{intensity}"
    return "v_" + hashlib.sha1(key.encode()).hexdigest()[:10]


def main():
    for seed in load_seeds():
        base = {
            "seed_id": seed["id"],
            "original": seed["text"],
            "label": seed["label"],
            "category": seed["category"],
        }
        if INCLUDE_CLEAN:
            print(json.dumps({**base, "id": variant_id(seed["id"], "clean", 0),
                              "text": seed["text"], "technique": "clean",
                              "intensity": 0}, ensure_ascii=False))
        for tname, fn in TRANSFORMS.items():
            for inten in INTENSITIES:
                out = fn(seed["text"], inten, seed=1234)
                print(json.dumps({**base, "id": variant_id(seed["id"], tname, inten),
                                  "text": out, "technique": tname,
                                  "intensity": inten}, ensure_ascii=False))


if __name__ == "__main__":
    main()
