"""07. 단순 연음 역복원을 lossy 후보로 명시적으로 활성화한다.

실행:
    python examples/07_liaison_provider.py
"""

from k_safeguard import Gateway
from k_safeguard.providers import LiaisonInverseProvider


def main() -> None:
    gateway = Gateway(providers=[LiaisonInverseProvider(max_candidates=9)])
    result = gateway.process("머글게")
    views = [view.text for view in result.views]

    print(f"view: {views}")
    assert views[0] == "머글게"
    assert "먹을게" in views
    assert any(view.lossy for view in result.views[1:])

    print("연음 후보는 원문을 덮어쓰지 않으며 기본 Gateway에는 연결되지 않습니다.")


if __name__ == "__main__":
    main()
