"""Пользователи, сессии и аудит: тонкий слой над SQLite.

Используется стандартный sqlite3 — лишних зависимостей не требуется.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .config import settings

# scrypt — встроен в hashlib, не требует внешних библиотек.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 64

_lock = threading.Lock()
_db_path: Path | None = None


def _connect() -> sqlite3.Connection:
    global _db_path
    if _db_path is None:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        _db_path = settings.data_dir / "app.db"
    connection = sqlite3.connect(_db_path, timeout=30, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def init_db() -> None:
    """Создаёт схему и первого администратора."""
    with _lock, _connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    NOT NULL UNIQUE,
                password_hash TEXT    NOT NULL,
                is_admin      INTEGER NOT NULL DEFAULT 0,
                created_at    REAL    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token      TEXT PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                username   TEXT,
                action     TEXT NOT NULL,
                path       TEXT,
                created_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_expires
                ON sessions(expires_at);
            """
        )

        count = connection.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        if count == 0:
            password = settings.admin_password or secrets.token_urlsafe(12)
            create_user(settings.admin_username, password, is_admin=True,
                        connection=connection)
            if not settings.admin_password:
                # Пароль сгенерирован — показываем один раз при первом старте.
                print(
                    "\n" + "=" * 62 + "\n"
                    "Создан администратор по умолчанию\n"
                    f"  логин:  {settings.admin_username}\n"
                    f"  пароль: {password}\n"
                    "Смените пароль или задайте ADMIN_PASSWORD в .env\n"
                    + "=" * 62 + "\n",
                    flush=True,
                )


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=_SCRYPT_N,
            r=_SCRYPT_R,
            p=_SCRYPT_P,
            dklen=_SCRYPT_DKLEN,
        )
    except (ValueError, TypeError):
        return False
    # Сравнение с постоянным временем — защита от timing-атак.
    return hmac.compare_digest(digest.hex(), digest_hex)


@dataclass
class User:
    id: int
    username: str
    is_admin: bool


def _row_to_user(row: sqlite3.Row) -> User:
    return User(id=row["id"], username=row["username"], is_admin=bool(row["is_admin"]))


def create_user(
    username: str,
    password: str,
    *,
    is_admin: bool = False,
    connection: sqlite3.Connection | None = None,
) -> User:
    username = username.strip()
    if not username or len(username) > 64:
        raise ValueError("Недопустимое имя пользователя")
    if len(password) < 8:
        raise ValueError("Пароль должен быть не короче 8 символов")

    own_connection = connection is None
    connection = connection or _connect()
    try:
        with _lock if own_connection else _nullcontext():
            cursor = connection.execute(
                "INSERT INTO users (username, password_hash, is_admin, created_at)"
                " VALUES (?, ?, ?, ?)",
                (username, hash_password(password), int(is_admin), time.time()),
            )
            connection.commit()
            return User(id=cursor.lastrowid, username=username, is_admin=is_admin)
    except sqlite3.IntegrityError as exc:
        raise ValueError("Пользователь с таким именем уже существует") from exc
    finally:
        if own_connection:
            connection.close()


class _nullcontext:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *exc_info: object) -> bool:
        return False


def authenticate(username: str, password: str) -> User | None:
    with _lock, _connect() as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE username = ?", (username.strip(),)
        ).fetchone()
    if row is None:
        # Всё равно считаем хеш — выравниваем время ответа.
        verify_password(password, hash_password("dummy-password"))
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return _row_to_user(row)


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = time.time()
    with _lock, _connect() as connection:
        connection.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at)"
            " VALUES (?, ?, ?, ?)",
            (token, user_id, now, now + settings.session_ttl_hours * 3600),
        )
        connection.commit()
    return token


def user_for_token(token: str) -> User | None:
    if not token:
        return None
    with _lock, _connect() as connection:
        row = connection.execute(
            """
            SELECT u.* FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ? AND s.expires_at > ?
            """,
            (token, time.time()),
        ).fetchone()
    return _row_to_user(row) if row else None


def destroy_session(token: str) -> None:
    with _lock, _connect() as connection:
        connection.execute("DELETE FROM sessions WHERE token = ?", (token,))
        connection.commit()


def purge_expired_sessions() -> None:
    with _lock, _connect() as connection:
        connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (time.time(),))
        connection.commit()


def change_password(user_id: int, new_password: str) -> None:
    if len(new_password) < 8:
        raise ValueError("Пароль должен быть не короче 8 символов")
    with _lock, _connect() as connection:
        connection.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(new_password), user_id),
        )
        # Разлогиниваем все сессии пользователя после смены пароля.
        connection.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        connection.commit()


def audit(username: str | None, action: str, path: str | None = None) -> None:
    try:
        with _lock, _connect() as connection:
            connection.execute(
                "INSERT INTO audit_log (username, action, path, created_at)"
                " VALUES (?, ?, ?, ?)",
                (username, action, path, time.time()),
            )
            connection.commit()
    except sqlite3.Error:
        # Аудит не должен ломать основную операцию.
        pass


def recent_audit(limit: int = 100) -> list[dict]:
    with _lock, _connect() as connection:
        rows = connection.execute(
            "SELECT username, action, path, created_at FROM audit_log"
            " ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
