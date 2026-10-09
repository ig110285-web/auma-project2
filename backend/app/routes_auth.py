"""Аутентификация: вход, выход, регистрация, смена пароля."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from . import database
from .config import settings
from .database import User
from .deps import SESSION_COOKIE, current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=256)


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,          # недоступна из JavaScript — защита от XSS-кражи
        samesite="lax",         # базовая защита от CSRF
        secure=False,           # включите True при работе строго по HTTPS
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )


@router.post("/login")
def login(payload: LoginRequest, response: Response) -> dict:
    user = database.authenticate(payload.username, payload.password)
    if user is None:
        # Одинаковый ответ для неверного логина и пароля.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
        )

    token = database.create_session(user.id)
    _set_session_cookie(response, token)
    database.audit(user.username, "login")
    return {"id": user.id, "username": user.username, "is_admin": user.is_admin}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.post("/register", status_code=201)
def register(payload: RegisterRequest, response: Response) -> dict:
    """Регистрация нового пользователя.

    По умолчанию выключена (ALLOW_REGISTRATION=false) — включайте осознанно.
    """
    if not settings.allow_registration:
        raise HTTPException(
            status_code=403,
            detail="Регистрация отключена. Обратитесь к администратору",
        )
    try:
        user = database.create_user(payload.username, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    token = database.create_session(user.id)
    _set_session_cookie(response, token)
    database.audit(user.username, "register")
    return {"id": user.id, "username": user.username, "is_admin": user.is_admin}


@router.get("/session")
def session_info(user: User = Depends(current_user)) -> dict:
    return {"id": user.id, "username": user.username, "is_admin": user.is_admin}
