"""05. 모호한 변형 정책 — 된소리·초성체는 여러 복원 view로 확장하지 않는다.

실행:
    python examples/05_ambiguous_policy.py
"""

from k_safeguard import Gateway


def main() -> None:
    gateway = Gateway()
    samples = ("씨스템 점검", "ㅅㅅㅌ 점검")

    for text in samples:
        result = gateway.process(text)
        print(f"입력: {text}")
        print(f"view: {[view.text for view in result.views]}")
        assert [view.text for view in result.views] == [text]

    print("된소리·초성체는 문맥 없이 확정하지 않고 원문만 보존합니다.")


if __name__ == "__main__":
    main()
