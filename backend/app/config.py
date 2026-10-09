"""Конфигурация приложения. Все значения читаются из переменных окружения."""

from __future__ import annotations

import os
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class Settings:
    """Настройки, собранные из окружения."""

    def __init__(self) -> None:
        # Корень, внутри которого разрешено работать с файлами.
        self.storage_root: Path = Path(
            os.getenv("STORAGE_ROOT", "/data")
        ).expanduser().resolve()

        # Каталог с SQLite-базой для пользователей и сессий.
        self.data_dir: Path = Path(
            os.getenv("DATA_DIR", "/app-data")
        ).expanduser().resolve()

        self.secret_key: str = os.getenv("SECRET_KEY", "change-me-in-production")

        # Первый администратор создаётся при старте, если база пуста.
        self.admin_username: str = os.getenv("ADMIN_USERNAME", "admin")
        self.admin_password: str = os.getenv("ADMIN_PASSWORD", "")

        # Ограничения.
        self.max_upload_mb: int = _env_int("MAX_UPLOAD_MB", 2048)
        self.default_quota_gb: int = _env_int("DEFAULT_QUOTA_GB", 0)  # 0 = без квоты
        self.allow_registration: bool = _env_bool("ALLOW_REGISTRATION", False)

        # Время жизни сессии в часах.
        self.session_ttl_hours: int = _env_int("SESSION_TTL_HOURS", 24 * 7)

        # Доверять ли заголовкам X-Forwarded-* от обратного прокси.
        self.trust_proxy: bool = _env_bool("TRUST_PROXY", True)

        # Отдавать ли фронтенд из собранной статики (продакшен-режим).
        self.static_dir: Path = Path(
            os.getenv("STATIC_DIR", "/app/static")
        ).expanduser()

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def default_quota_bytes(self) -> int:
        return self.default_quota_gb * 1024 * 1024 * 1024


settings = Settings()
