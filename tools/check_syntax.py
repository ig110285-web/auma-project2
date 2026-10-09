"""Проверка синтаксиса всех модулей проекта.

Запуск: python tools/check_syntax.py
"""

from __future__ import annotations

import ast
import pathlib
import sys


def main() -> int:
    root = pathlib.Path(__file__).resolve().parent.parent
    targets = list(root.glob("backend/app/**/*.py")) + \
        list(root.glob("backend/tests/**/*.py"))

    failures = 0
    for path in targets:
        try:
            ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            failures += 1
            print(f"SYNTAX ERROR: {path.relative_to(root)}: {exc}")

    print(f"Checked {len(targets)} files, failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
