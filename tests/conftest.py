"""hf_repo(레포 루트의 src/ 바깥 패키지)를 어떤 실행 컨텍스트에서도 import 가능하게 한다.

mutmut은 mutants/tests/처럼 tests/를 격리된 복사본으로 옮겨 실행하는데, 그
복사본 트리 안에는 src/ 바깥에 있는 hf_repo/가 포함되지 않는다. 이 파일
위치를 기준으로 상위 디렉터리를 거슬러 올라가며 hf_repo/가 실제로 존재하는
디렉터리(진짜 레포 루트)를 찾아 sys.path에 추가한다. mutmut의 mutants/
디렉터리는 항상 진짜 레포 루트 아래에 생성되므로 이 방식은 정상 실행과
mutmut 격리 실행 양쪽 모두에서 동작한다. unittest에는 영향이 없다(conftest.py
는 pytest 전용 훅이라 `python -m unittest discover`에서는 로드되지 않는다).
"""

from __future__ import annotations

import sys
from pathlib import Path

_here = Path(__file__).resolve()
for _candidate in (_here, *_here.parents):
    if (_candidate / "hf_repo").is_dir():
        if str(_candidate) not in sys.path:
            sys.path.insert(0, str(_candidate))
        break
