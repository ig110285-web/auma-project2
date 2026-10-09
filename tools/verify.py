#!/usr/bin/env python
"""Проверка целостности проекта: наличие файлов, синтаксис, валидность JSON.

Запуск: python tools/verify.py
"""

from __future__ import annotations

import ast
import json
import pathlib
import sys

REQUIRED_FILES = [
    # Backend
    "backend/app/__init__.py",
    "backend/app/main.py",
    "backend/app/config.py",
    "backend/app/database.py",
    "backend/app/deps.py",
    "backend/app/storage.py",
    "backend/app/routes_auth.py",
    "backend/app/routes_files.py",
    "backend/requirements.txt",
    "backend/requirements-dev.txt",
    "backend/Dockerfile",
    "backend/tests/test_api.py",
    "backend/tests/test_storage.py",
    # Frontend
    "frontend/package.json",
    "frontend/vite.config.js",
    "frontend/index.html",
    "frontend/src/main.jsx",
    "frontend/src/App.jsx",
    "frontend/src/api.js",
    "frontend/src/styles.css",
    "frontend/Dockerfile",
    # Инфраструктура
    "Dockerfile",
    "docker-compose.yml",
    "Caddyfile",
    ".env.example",
    ".gitignore",
    "README.md",
]


def main() -> int:
    root = pathlib.Path(__file__).resolve().parent.parent
    problems: list[str] = []

    print("=== Структура проекта ===")
    for relative in REQUIRED_FILES:
        if not (root / relative).is_file():
            problems.append(f"отсутствует файл: {relative}")
            print(f"  ОТСУТСТВУЕТ: {relative}")
    if not problems:
        print(f"  Все {len(REQUIRED_FILES)} файлов на месте")

    print("\n=== Синтаксис Python ===")
    python_files = sorted(
        list(root.glob("backend/app/**/*.py"))
        + list(root.glob("backend/tests/**/*.py"))
        + list(root.glob("tools/*.py"))
    )
    syntax_failures = 0
    for path in python_files:
        try:
            ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            syntax_failures += 1
            problems.append(f"синтаксическая ошибка: {path.name}: {exc}")
            print(f"  ОШИБКА: {path.relative_to(root)}: {exc}")
    print(f"  Проверено {len(python_files)} файлов, ошибок: {syntax_failures}")

    print("\n=== JSON-файлы ===")
    for relative in ["frontend/package.json"]:
        path = root / relative
        try:
            json.loads(path.read_text(encoding="utf-8"))
            print(f"  OK: {relative}")
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"невалидный JSON: {relative}: {exc}")
            print(f"  ОШИБКА: {relative}: {exc}")

    print("\n=== Обязательные настройки в .env.example ===")
    env_text = (root / ".env.example").read_text(encoding="utf-8")
    for key in ["ADMIN_PASSWORD", "SECRET_KEY", "STORAGE_ROOT",
                "MAX_UPLOAD_MB", "APP_PORT"]:
        if f"{key}=" not in env_text:
            problems.append(f"в .env.example нет {key}")
            print(f"  ОТСУТСТВУЕТ: {key}")
        else:
            print(f"  OK: {key}")

    print("\n" + "=" * 50)
    if problems:
        print(f"Итог: найдено проблем — {len(problems)}")
        for item in problems:
            print(f"  - {item}")
        return 1

    print("Итог: все проверки пройдены")
    return 0


if __name__ == "__main__":
    sys.exit(main())
