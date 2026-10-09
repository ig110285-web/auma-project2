"""Тесты безопасности хранилища: path traversal, лимиты, базовые операции.

Запуск: pytest -q (из каталога backend)
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# Изолируем хранилище ДО импорта приложения.
_TMP = tempfile.mkdtemp(prefix="fm-test-")
os.environ["STORAGE_ROOT"] = _TMP
os.environ["DATA_DIR"] = os.path.join(_TMP, "_data")
os.environ["SECRET_KEY"] = "test-secret"

from app import storage  # noqa: E402
from app.config import settings  # noqa: E402


@pytest.fixture(autouse=True)
def clean_storage():
    """Чистит корень хранилища между тестами."""
    root = Path(_TMP)
    for child in root.iterdir():
        if child.name == "_data":
            continue
        if child.is_dir():
            import shutil

            shutil.rmtree(child)
        else:
            child.unlink()
    root.mkdir(parents=True, exist_ok=True)
    yield


def test_resolve_rejects_parent_traversal():
    with pytest.raises(storage.PathTraversalError):
        storage.resolve("../etc/passwd")


def test_resolve_rejects_nested_traversal():
    with pytest.raises(storage.PathTraversalError):
        storage.resolve("docs/../../secret")


def test_resolve_rejects_absolute_path():
    resolved = storage.resolve("/etc/passwd", must_exist=False)
    assert str(resolved).startswith(str(Path(_TMP).resolve()))


def test_resolve_normalizes_backslashes():
    resolved = storage.resolve("a\\b\\c", must_exist=False)
    assert resolved.name == "c"
    assert resolved.parent.name == "b"


def test_empty_path_is_root():
    assert storage.resolve("") == Path(_TMP).resolve()


def test_upload_download_roundtrip():
    entry = storage.save_upload("", "hello.txt", iter([b"hello ", b"world"]))
    assert entry.name == "hello.txt"
    assert entry.size == 11
    assert storage.resolve("hello.txt").read_bytes() == b"hello world"


def test_upload_rejects_duplicate():
    storage.save_upload("", "dup.txt", iter([b"x"]))
    with pytest.raises(storage.ConflictError):
        storage.save_upload("", "dup.txt", iter([b"y"]))


def test_upload_strips_directory_from_filename():
    entry = storage.save_upload("", "../../evil.txt", iter([b"x"]))
    assert entry.name == "evil.txt"
    assert storage.resolve("evil.txt").exists()
    assert not (Path(_TMP).parent / "evil.txt").exists()


def test_upload_enforces_size_limit():
    original = settings.max_upload_mb
    settings.max_upload_mb = 0  # 0 МБ -> любой байт превышает лимит
    try:
        with pytest.raises(storage.StorageError):
            storage.save_upload("", "big.bin", iter([b"x"]))
    finally:
        settings.max_upload_mb = original


def test_make_dir_and_list():
    storage.make_dir("docs")
    storage.make_dir("docs/nested")
    entries = storage.list_dir("")
    assert [e.name for e in entries] == ["docs"]
    assert entries[0].is_dir
    nested = storage.list_dir("docs")
    assert [e.name for e in nested] == ["nested"]


def test_rename_within_directory():
    storage.save_upload("", "old.txt", iter([b"x"]))
    entry = storage.rename("old.txt", "new.txt")
    assert entry.name == "new.txt"
    assert storage.resolve("new.txt").exists()


def test_rename_rejects_path_separator():
    storage.save_upload("", "a.txt", iter([b"x"]))
    with pytest.raises(storage.StorageError):
        storage.rename("a.txt", "../escape.txt")


def test_rename_rejects_sibling_traversal():
    """Имя вида `../sibling` не должно уводить за пределы каталога."""
    storage.make_dir("inner")
    storage.save_upload("", "inner/file.txt", iter([b"x"]))
    with pytest.raises(storage.StorageError):
        storage.rename("inner/file.txt", "../escaped.txt")
    assert storage.resolve("inner/file.txt").exists()
    assert not storage.resolve("escaped.txt", must_exist=False).exists()


def test_move_between_directories():
    storage.make_dir("target")
    storage.save_upload("", "file.txt", iter([b"x"]))
    entry = storage.move("file.txt", "target")
    assert entry.path == "target/file.txt"


def test_move_rejects_directory_into_itself():
    storage.make_dir("outer")
    storage.make_dir("outer/inner")
    with pytest.raises(storage.StorageError):
        storage.move("outer", "outer/inner")


def test_delete_removes_directory_recursively():
    storage.make_dir("doomed")
    storage.save_upload("doomed", "f.txt", iter([b"x"]))
    storage.delete("doomed")
    assert not storage.resolve("doomed", must_exist=False).exists()


def test_delete_refuses_root():
    with pytest.raises(storage.StorageError):
        storage.delete("")


def test_hidden_files_are_not_listed():
    storage.save_upload("", "visible.txt", iter([b"x"]))
    storage.save_upload("", ".secret", iter([b"x"]))
    names = [e.name for e in storage.list_dir("")]
    assert "visible.txt" in names
    assert ".secret" not in names


def test_storage_usage_counts_files():
    storage.save_upload("", "one.txt", iter([b"12345"]))
    storage.make_dir("sub")
    storage.save_upload("sub", "two.txt", iter([b"123"]))
    total, count = storage.storage_usage()
    assert count == 2
    assert total == 8
