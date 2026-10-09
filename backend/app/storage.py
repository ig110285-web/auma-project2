"""Безопасная работа с файловой системой.

Ключевой принцип: любой путь, пришедший от клиента, нормализуется и
проверяется на принадлежность корню хранилища. Это защита от path
traversal (`../`), от абсолютных путей и от symlink-выходов наружу.
"""

from __future__ import annotations

import os
import shutil
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .config import settings


class StorageError(Exception):
    """Ошибка работы с хранилищем, безопасная для показа клиенту."""


class PathTraversalError(StorageError):
    """Попытка выйти за пределы корня хранилища."""


class NotFoundError(StorageError):
    """Запрошенный объект не существует."""


class ConflictError(StorageError):
    """Конфликт: имя занято, папка не пуста и т.п."""


def _normalize_relative(relative: str) -> str:
    """Приводит клиентский путь к нормализованному относительному виду.

    Отбрасывает пустые сегменты, `.` и запрещает `..`.
    """
    if relative is None:
        return ""

    # Юникод-нормализация отсекает трюки с похожими символами.
    relative = unicodedata.normalize("NFC", relative)
    relative = relative.replace("\\", "/").strip()
    relative = relative.lstrip("/")

    parts: list[str] = []
    for raw_part in relative.split("/"):
        part = raw_part.strip()
        if part in ("", "."):
            continue
        if part == "..":
            raise PathTraversalError("Переход в родительский каталог запрещён")
        if "\x00" in part:
            raise StorageError("Недопустимый символ в пути")
        parts.append(part)

    return "/".join(parts)


def resolve(relative: str = "", *, must_exist: bool = True) -> Path:
    """Возвращает абсолютный путь внутри корня хранилища.

    Проверяет, что итоговый путь действительно лежит под storage_root,
    в том числе после разыменования символических ссылок.
    """
    clean = _normalize_relative(relative)
    root = settings.storage_root
    candidate = (root / clean).resolve() if clean else root.resolve()

    root_resolved = root.resolve()

    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise PathTraversalError("Путь выходит за пределы хранилища")

    if must_exist and not candidate.exists():
        raise NotFoundError("Файл или папка не найдены")

    return candidate


def relative_to_root(path: Path) -> str:
    """Обратное преобразование: абсолютный путь -> относительный от корня."""
    root = settings.storage_root.resolve()
    try:
        rel = path.resolve().relative_to(root)
    except ValueError as exc:  # pragma: no cover - защитная ветка
        raise PathTraversalError("Путь вне хранилища") from exc
    return "" if str(rel) == "." else rel.as_posix()


@dataclass
class Entry:
    """Описание одного элемента в листинге."""

    name: str
    path: str
    is_dir: bool
    size: int
    modified: str
    mime: str | None = None

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "path": self.path,
            "is_dir": self.is_dir,
            "size": self.size,
            "modified": self.modified,
            "mime": self.mime,
        }


def _modified_iso(stat_result: os.stat_result) -> str:
    return datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc).isoformat()


def _entry_for(path: Path) -> Entry:
    stat_result = path.stat()
    is_dir = path.is_dir()
    return Entry(
        name=path.name,
        path=relative_to_root(path),
        is_dir=is_dir,
        size=0 if is_dir else stat_result.st_size,
        modified=_modified_iso(stat_result),
        mime=None if is_dir else guess_mime(path.name),
    )


def list_dir(relative: str = "") -> list[Entry]:
    """Список содержимого каталога: сначала папки, затем файлы, по алфавиту."""
    directory = resolve(relative)
    if not directory.is_dir():
        raise StorageError("Указанный путь не является каталогом")

    entries: list[Entry] = []
    for child in directory.iterdir():
        # Скрытые файлы и битые ссылки пропускаем.
        if child.name.startswith("."):
            continue
        try:
            if child.is_symlink() and not child.exists():
                continue
            entries.append(_entry_for(child))
        except OSError:
            continue

    entries.sort(key=lambda item: (not item.is_dir, item.name.lower()))
    return entries


def storage_usage(relative: str = "") -> tuple[int, int]:
    """Возвращает (суммарный размер в байтах, количество файлов)."""
    base = resolve(relative)
    total = 0
    count = 0
    for path in _walk(base):
        try:
            if path.is_file():
                total += path.stat().st_size
                count += 1
        except OSError:
            continue
    return total, count


def _walk(base: Path) -> Iterator[Path]:
    """Обход дерева без выхода за пределы корня."""
    root = settings.storage_root.resolve()
    stack = [base]
    while stack:
        current = stack.pop()
        try:
            children = list(current.iterdir())
        except OSError:
            continue
        for child in children:
            if child.name.startswith("."):
                continue
            try:
                resolved = child.resolve()
            except OSError:
                continue
            if resolved != root and root not in resolved.parents:
                continue  # symlink наружу — игнорируем
            yield child
            if child.is_dir() and not child.is_symlink():
                stack.append(child)


def make_dir(relative: str) -> Entry:
    """Создаёт каталог. Родитель должен существовать."""
    target = resolve(relative, must_exist=False)
    if target.exists():
        raise ConflictError("Объект с таким именем уже существует")
    parent = target.parent
    if not parent.is_dir():
        raise NotFoundError("Родительский каталог не найден")
    target.mkdir()
    return _entry_for(target)


def rename(old_relative: str, new_name: str) -> Entry:
    """Переименовывает объект внутри его текущего каталога.

    Имя проверяется строго: разделители пути, `..` и пустая строка
    отклоняются, поэтому выйти за пределы каталога этим вызовом нельзя.
    """
    new_name = new_name.strip().strip("/")
    if not new_name or "/" in new_name or "\\" in new_name or new_name == "..":
        raise StorageError("Недопустимое имя")

    source = resolve(old_relative)
    if source == settings.storage_root.resolve():
        raise StorageError("Нельзя переименовать корень хранилища")

    destination = source.parent / new_name

    # Финальная страховка: назначение обязано остаться под корнем хранилища.
    root_resolved = settings.storage_root.resolve()
    if destination.resolve() != root_resolved and \
            root_resolved not in destination.resolve().parents:
        raise PathTraversalError("Путь выходит за пределы хранилища")

    if destination.exists():
        raise ConflictError("Объект с таким именем уже существует")

    source.rename(destination)
    return _entry_for(destination)


def move(source_relative: str, destination_dir_relative: str) -> Entry:
    """Перемещает объект в другой каталог, сохраняя имя."""
    source = resolve(source_relative)
    if source == settings.storage_root.resolve():
        raise StorageError("Нельзя переместить корень хранилища")

    destination_dir = resolve(destination_dir_relative)
    if not destination_dir.is_dir():
        raise NotFoundError("Каталог назначения не найден")

    # Перемещение в тот же каталог — no-op, а не ошибка «имя занято».
    if destination_dir == source.parent:
        return _entry_for(source)

    destination = destination_dir / source.name

    # Запрет переместить папку внутрь самой себя.
    if source.is_dir():
        try:
            destination.resolve().relative_to(source.resolve())
        except ValueError:
            pass
        else:
            raise StorageError("Нельзя переместить папку внутрь себя")

    if destination.exists():
        raise ConflictError("В каталоге назначения уже есть объект с таким именем")

    source.rename(destination)
    return _entry_for(destination)


def delete(relative: str) -> None:
    """Удаляет файл или каталог (рекурсивно)."""
    target = resolve(relative)
    if target == settings.storage_root.resolve():
        raise StorageError("Нельзя удалить корень хранилища")
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()


def _quota_exceeded(additional_bytes: int) -> bool:
    quota = settings.default_quota_bytes
    if quota <= 0:
        return False
    return storage_usage()[0] + additional_bytes > quota


def save_upload(relative_dir: str, filename: str, chunks: Iterator[bytes]) -> Entry:
    """Потоково сохраняет загруженный файл, не держа его целиком в памяти."""
    safe_name = Path(filename.replace("\\", "/")).name.strip()
    if not safe_name or safe_name in (".", ".."):
        raise StorageError("Недопустимое имя файла")

    directory = resolve(relative_dir)
    if not directory.is_dir():
        raise NotFoundError("Каталог назначения не найден")

    target = resolve(
        f"{relative_dir}/{safe_name}" if relative_dir else safe_name,
        must_exist=False,
    )
    if target.exists():
        raise ConflictError("Файл с таким именем уже существует")

    written = 0
    temp_path = target.with_name(target.name + ".part")
    try:
        with temp_path.open("wb") as handle:
            for chunk in chunks:
                written += len(chunk)
                if written > settings.max_upload_bytes:
                    raise StorageError(
                        f"Файл превышает лимит {settings.max_upload_mb} МБ"
                    )
                handle.write(chunk)

        if _quota_exceeded(written):
            raise StorageError("Превышена квота хранилища")

        temp_path.replace(target)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    return _entry_for(target)


# --- Определение MIME-типа -------------------------------------------------

_EXTRA_MIME = {
    ".md": "text/markdown",
    ".py": "text/x-python",
    ".js": "text/javascript",
    ".ts": "text/typescript",
    ".tsx": "text/typescript",
    ".json": "application/json",
    ".yml": "text/yaml",
    ".yaml": "text/yaml",
    ".toml": "text/plain",
    ".sh": "text/x-shellscript",
    ".rs": "text/x-rust",
    ".go": "text/x-go",
    ".java": "text/x-java",
    ".sql": "text/x-sql",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def guess_mime(name: str) -> str:
    import mimetypes

    ext = Path(name).suffix.lower()
    if ext in _EXTRA_MIME:
        return _EXTRA_MIME[ext]
    guessed, _ = mimetypes.guess_type(name)
    return guessed or "application/octet-stream"


TEXT_MIME_PREFIXES = ("text/",)
TEXT_MIME_EXACT = {
    "application/json",
    "application/xml",
    "application/javascript",
    "application/x-yaml",
    "application/x-sh",
    "application/sql",
}
