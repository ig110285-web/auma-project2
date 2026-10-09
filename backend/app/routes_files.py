"""HTTP-роуты файлового менеджера."""

from __future__ import annotations

import io
import mimetypes
import zipfile
from typing import Iterator

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import database, storage
from .config import settings
from .deps import current_user
from .database import User

router = APIRouter(prefix="/api", tags=["files"])

# Порог, выше которого файл не отдаём в превью целиком.
PREVIEW_MAX_BYTES = 2 * 1024 * 1024


def _storage_http_error(exc: storage.StorageError) -> HTTPException:
    """Преобразует доменную ошибку в HTTP-ответ с осмысленным кодом."""
    if isinstance(exc, storage.PathTraversalError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, storage.NotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, storage.ConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


# --- Модели запросов -------------------------------------------------------


class CreateFolderRequest(BaseModel):
    path: str = Field(default="", description="Каталог, где создаётся папка")
    name: str = Field(min_length=1, max_length=255)


class RenameRequest(BaseModel):
    path: str = Field(min_length=1)
    new_name: str = Field(min_length=1, max_length=255)


class MoveRequest(BaseModel):
    path: str = Field(min_length=1)
    destination: str = Field(default="")


class DeleteRequest(BaseModel):
    paths: list[str] = Field(min_length=1)


class DownloadRequest(BaseModel):
    paths: list[str] = Field(min_length=1)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=256)


# --- Листинг и статистика --------------------------------------------------


@router.get("/files")
def list_files(path: str = Query(default=""),
               user: User = Depends(current_user)) -> dict:
    """Содержимое каталога плюс информация о текущем пути."""
    try:
        entries = storage.list_dir(path)
        current = storage.relative_to_root(storage.resolve(path))
    except storage.StorageError as exc:
        raise _storage_http_error(exc) from exc

    return {
        "path": current,
        "parent": current.rsplit("/", 1)[0] if "/" in current else "",
        "entries": [entry.as_dict() for entry in entries],
    }


@router.get("/stats")
def stats(path: str = Query(default=""),
          user: User = Depends(current_user)) -> dict:
    """Размер и количество файлов в поддереве."""
    try:
        total, count = storage.storage_usage(path)
    except storage.StorageError as exc:
        raise _storage_http_error(exc) from exc
    quota = settings.default_quota_bytes
    return {
        "total_bytes": total,
        "file_count": count,
        "quota_bytes": quota,
        "max_upload_bytes": settings.max_upload_bytes,
    }


@router.get("/search")
def search(q: str = Query(min_length=1, max_length=128),
           path: str = Query(default=""),
           user: User = Depends(current_user)) -> dict:
    """Рекурсивный поиск по подстроке в имени."""
    needle = q.lower()
    try:
        base = storage.resolve(path)
    except storage.StorageError as exc:
        raise _storage_http_error(exc) from exc

    results: list[dict] = []
    for item in storage._walk(base):
        if needle in item.name.lower():
            try:
                results.append(storage._entry_for(item).as_dict())
            except OSError:
                continue
        if len(results) >= 500:
            break
    return {"query": q, "results": results, "truncated": len(results) >= 500}


# --- Создание, переименование, перемещение, удаление -----------------------


@router.post("/folders", status_code=201)
def create_folder(payload: CreateFolderRequest,
                  user: User = Depends(current_user)) -> dict:
    name = payload.name.strip().strip("/")
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        raise HTTPException(status_code=400, detail="Недопустимое имя папки")
    target = f"{payload.path}/{name}" if payload.path else name
    try:
        entry = storage.make_dir(target)
    except storage.StorageError as exc:
        raise _storage_http_error(exc) from exc
    database.audit(user.username, "create_folder", entry.path)
    return entry.as_dict()


@router.post("/rename")
def rename(payload: RenameRequest, user: User = Depends(current_user)) -> dict:
    """Переименование внутри текущего каталога.

    Ограничение намеренное: эндпоинт не умеет менять расположение файла,
    поэтому обойти каталог через подставное имя невозможно.
    """
    new_name = payload.new_name.strip()
    if not new_name or "/" in new_name or "\\" in new_name or new_name in (".", ".."):
        raise HTTPException(status_code=400, detail="Недопустимое имя")
    try:
        entry = storage.rename(payload.path, new_name)
    except storage.StorageError as exc:
        raise _storage_http_error(exc) from exc
    database.audit(user.username, "rename", f"{payload.path} -> {entry.path}")
    return entry.as_dict()


@router.post("/move")
def move(payload: MoveRequest, user: User = Depends(current_user)) -> dict:
    try:
        entry = storage.move(payload.path, payload.destination)
    except storage.StorageError as exc:
        raise _storage_http_error(exc) from exc
    database.audit(user.username, "move", f"{payload.path} -> {entry.path}")
    return entry.as_dict()


@router.post("/delete")
def delete(payload: DeleteRequest, user: User = Depends(current_user)) -> dict:
    """Удаляет переданные пути, возвращая отчёт по каждому.

    Не останавливается на первой ошибке: клиент получает полную картину.
    """
    results: list[dict] = []
    for item in payload.paths:
        try:
            storage.delete(item)
            database.audit(user.username, "delete", item)
            results.append({"path": item, "ok": True})
        except storage.StorageError as exc:
            results.append({"path": item, "ok": False, "error": str(exc)})
    failed = [item for item in results if not item["ok"]]
    return {"results": results, "deleted": len(results) - len(failed),
            "failed": len(failed)}


# --- Загрузка и скачивание -------------------------------------------------


def _upload_chunks(upload: UploadFile) -> Iterator[bytes]:
    """Читает загружаемый файл порциями, не загружая его целиком в память."""
    while True:
        chunk = upload.file.read(1024 * 1024)
        if not chunk:
            break
        yield chunk


@router.post("/upload", status_code=201)
async def upload(path: str = Form(default=""),
                 files: list[UploadFile] = File(...),
                 user: User = Depends(current_user)) -> dict:
    """Загрузка одного или нескольких файлов в указанный каталог."""
    saved: list[dict] = []
    failed: list[dict] = []

    for upload_file in files:
        filename = upload_file.filename or "unnamed"
        try:
            entry = storage.save_upload(path, filename, _upload_chunks(upload_file))
            database.audit(user.username, "upload", entry.path)
            saved.append(entry.as_dict())
        except storage.StorageError as exc:
            failed.append({"name": filename, "error": str(exc)})
        finally:
            await upload_file.close()

    if not saved and failed:
        first_error = failed[0]["error"]
        status = 409 if "уже существует" in first_error else 400
        return JSONResponse(status_code=status,
                            content={"saved": saved, "failed": failed})

    return {"saved": saved, "failed": failed}


@router.get("/download")
def download(path: str = Query(min_length=1),
             user: User = Depends(current_user)) -> FileResponse:
    """Скачивание одного файла."""
    try:
        target = storage.resolve(path)
    except storage.StorageError as exc:
        raise _storage_http_error(exc) from exc

    if target.is_dir():
        raise HTTPException(
            status_code=400,
            detail="Это папка. Используйте архивирование для скачивания папок",
        )

    database.audit(user.username, "download", path)
    media_type = storage.guess_mime(target.name)
    return FileResponse(
        target,
        media_type=media_type,
        filename=target.name,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.post("/download-zip")
def download_zip(payload: DownloadRequest,
                 user: User = Depends(current_user)) -> StreamingResponse:
    """Отдаёт выбранные файлы и папки одним zip-архивом."""
    targets = []
    for item in payload.paths:
        try:
            targets.append(storage.resolve(item))
        except storage.StorageError as exc:
            raise _storage_http_error(exc) from exc

    if not targets:
        raise HTTPException(status_code=400, detail="Нечего архивировать")

    archive_name = (
        targets[0].name + ".zip" if len(targets) == 1 else "selection.zip"
    )

    def build_archive() -> Iterator[bytes]:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for target in targets:
                # Файл кладём под его собственным именем.
                if target.is_file():
                    archive.write(target, arcname=target.name)
                    continue
                # Папку — со всеми вложенными элементами, сохраняя структуру.
                # base.parent даёт префикс, включающий имя самой папки.
                base = target.parent
                for nested in storage._walk(target):
                    arcname = nested.relative_to(base).as_posix()
                    archive.write(nested, arcname=arcname)
        buffer.seek(0)
        while True:
            chunk = buffer.read(1024 * 1024)
            if not chunk:
                break
            yield chunk

    database.audit(user.username, "download_zip", ", ".join(payload.paths))
    return StreamingResponse(
        build_archive(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{archive_name}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/preview")
def preview(path: str = Query(min_length=1),
            user: User = Depends(current_user)) -> dict:
    """Текстовое содержимое файла для встроенного просмотра."""
    try:
        target = storage.resolve(path)
    except storage.StorageError as exc:
        raise _storage_http_error(exc) from exc

    if target.is_dir():
        raise HTTPException(status_code=400, detail="Это папка")

    size = target.stat().st_size
    media_type = storage.guess_mime(target.name)
    is_text = media_type.startswith(storage.TEXT_MIME_PREFIXES) or \
        media_type in storage.TEXT_MIME_EXACT

    if size > PREVIEW_MAX_BYTES:
        return {"path": path, "mime": media_type, "size": size,
                "truncated": True, "text": None,
                "reason": "Файл слишком большой для предпросмотра"}

    if not is_text:
        return {"path": path, "mime": media_type, "size": size,
                "truncated": False, "text": None,
                "reason": "Предпросмотр недоступен для этого типа файлов"}

    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Ошибка чтения: {exc}") from exc

    return {"path": path, "mime": media_type, "size": size,
            "truncated": False, "text": text}


# --- Аккаунт ---------------------------------------------------------------


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return {"id": user.id, "username": user.username, "is_admin": user.is_admin}


@router.post("/me/password")
def change_password(payload: ChangePasswordRequest,
                    user: User = Depends(current_user)) -> dict:
    if database.authenticate(user.username, payload.current_password) is None:
        raise HTTPException(status_code=403, detail="Неверный текущий пароль")
    try:
        database.change_password(user.id, payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "message": "Пароль изменён, войдите заново"}


@router.get("/audit")
def audit_log(limit: int = Query(default=100, ge=1, le=1000),
              user: User = Depends(current_user)) -> dict:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Доступно только администратору")
    return {"items": database.recent_audit(limit)}
