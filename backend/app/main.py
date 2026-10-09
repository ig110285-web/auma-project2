"""Точка входа FastAPI-приложения файлового менеджера."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import routes_auth, routes_files
from .config import settings
from .database import init_db, purge_expired_sessions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("filemanager")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Подготовка хранилища и базы при старте."""
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    purge_expired_sessions()
    logger.info("Хранилище: %s", settings.storage_root)
    logger.info("Лимит загрузки: %s МБ", settings.max_upload_mb)
    yield


app = FastAPI(
    title="AUMA File Manager",
    description="Веб-файловый менеджер: загрузка, скачивание, управление файлами",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS нужен только для локальной разработки, когда Vite и API на разных портах.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_auth.router)
app.include_router(routes_files.router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Базовые защитные заголовки для всех ответов."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


@app.get("/healthz", tags=["service"])
def healthz() -> dict:
    return {"status": "ok"}


# --- Отдача собранного фронтенда (продакшен) -------------------------------

if settings.static_dir.is_dir():
    assets_dir = settings.static_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    index_file = settings.static_dir / "index.html"

    @app.get("/", include_in_schema=False)
    def serve_index() -> FileResponse:
        return FileResponse(index_file)

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        """SPA-роутинг: неизвестные пути отдают index.html.

        Пути /api/* сюда не попадают — они обрабатываются роутерами выше.
        """
        candidate = (settings.static_dir / full_path).resolve()
        static_root = settings.static_dir.resolve()
        if static_root in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_file)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": "Не найдено"})
