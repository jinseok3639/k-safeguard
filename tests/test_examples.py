"""examples/의 예제 스크립트가 실제로 끝까지 실행되는지 확인한다.

예제는 사용자가 가장 먼저 읽고 복사하는 코드라 API가 바뀌면 가장 먼저 낡는다.
subprocess 대신 in-process로 실행해 콘솔 인코딩(Windows cp949 등)과 무관하게
어디서나 같은 결과를 내도록 했다.
"""

from __future__ import annotations

import contextlib
import io
import json
import runpy
import unittest
from pathlib import Path


def _find_examples_dir() -> Path:
    """mutmut의 mutants/ 격리 실행에서도 실제 examples/를 찾는다(conftest.py와 같은 방식)."""
    here = Path(__file__).resolve()
    for candidate in here.parents:
        examples = candidate / "examples"
        if examples.is_dir():
            return examples
    raise FileNotFoundError("examples 디렉터리를 찾지 못했습니다.")


class ExampleScriptTest(unittest.TestCase):
    def test_every_example_runs_and_prints_output(self) -> None:
        # Given
        scripts = sorted(_find_examples_dir().glob("*.py"))
        self.assertTrue(scripts, "examples/에 실행할 예제가 없습니다.")
        # When / Then
        for script in scripts:
            with self.subTest(example=script.name):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    runpy.run_path(str(script), run_name="__main__")
                self.assertTrue(stdout.getvalue().strip())

    def test_demo_notebook_has_unique_cells_and_compilable_code(self) -> None:
        notebook_path = _find_examples_dir() / "demo" / "k_safeguard_demo.ipynb"
        notebook = json.loads(notebook_path.read_text(encoding="utf-8"))

        self.assertEqual(notebook["nbformat"], 4)
        cells = notebook["cells"]
        cell_ids = [cell["id"] for cell in cells]
        self.assertEqual(len(cell_ids), len(set(cell_ids)))

        code_cells = [cell for cell in cells if cell["cell_type"] == "code"]
        self.assertTrue(code_cells)
        for index, cell in enumerate(code_cells, start=1):
            with self.subTest(cell=cell["id"]):
                compile(
                    "".join(cell["source"]),
                    f"{notebook_path.name}:cell-{index}",
                    "exec",
                )


if __name__ == "__main__":
    unittest.main()
