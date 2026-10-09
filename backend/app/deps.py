"""Зависимости FastAPI: текущий пользователь и проверка прав."""

from __future__ import annotations

from fastapi import Cookie, HTTPException, status

from .database import User, user_for_token

SESSION_COOKIE = "fm_session"


def current_user(
    fm_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> User:
    """Достаёт пользователя по httpOnly-cookie с токеном сессии."""
    user = user_for_token(fm_session or "")
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация",
        )
    return user
