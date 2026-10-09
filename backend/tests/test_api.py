"""API-тесты: авторизация и защита эндпоинтов."""

from __future__ import annotations

import os
import tempfile

import pytest

_TMP = tempfile.mkdtemp(prefix="fm-api-")
os.environ["STORAGE_ROOT"] = _TMP
os.environ["DATA_DIR"] = os.path.join(_TMP, "_data")
os.environ["SECRET_KEY"] = "test-secret"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "supersecret123"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_files_require_auth(client):
    response = client.get("/api/files")
    assert response.status_code == 401


def test_upload_requires_auth(client):
    response = client.post("/api/upload", files={"files": ("a.txt", b"x")})
    assert response.status_code == 401


def test_login_rejects_wrong_password(client):
    response = client.post(
        "/api/auth/login", json={"username": "admin", "password": "wrong-password"}
    )
    assert response.status_code == 401


def test_login_sets_httponly_cookie(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "supersecret123"},
    )
    assert response.status_code == 200
    cookie_header = response.headers.get("set-cookie", "")
    assert "fm_session=" in cookie_header
    assert "HttpOnly" in cookie_header


def test_registration_disabled_by_default(client):
    response = client.post(
        "/api/auth/register", json={"username": "newbie", "password": "password123"}
    )
    assert response.status_code == 403


def test_full_file_lifecycle(client):
    """Вход, создание папки, загрузка, листинг, переименование, удаление."""
    client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "supersecret123"},
    )

    assert client.post("/api/folders", json={"path": "", "name": "docs"}).status_code == 201

    upload = client.post(
        "/api/upload",
        data={"path": "docs"},
        files={"files": ("note.txt", b"content here")},
    )
    assert upload.status_code == 201
    assert upload.json()["saved"][0]["path"] == "docs/note.txt"

    listing = client.get("/api/files", params={"path": "docs"}).json()
    assert [item["name"] for item in listing["entries"]] == ["note.txt"]

    renamed = client.post(
        "/api/rename", json={"path": "docs/note.txt", "new_name": "renamed.txt"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["path"] == "docs/renamed.txt"

    preview = client.get("/api/preview", params={"path": "docs/renamed.txt"}).json()
    assert preview["text"] == "content here"

    deleted = client.post("/api/delete", json={"paths": ["docs"]}).json()
    assert deleted["deleted"] == 1


def test_traversal_attempt_is_blocked(client):
    client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "supersecret123"},
    )
    response = client.get("/api/files", params={"path": "../../../etc"})
    assert response.status_code in (400, 403, 404)


def test_download_returns_file(client):
    client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "supersecret123"},
    )
    client.post("/api/upload", data={"path": ""},
                files={"files": ("dl.txt", b"payload")})
    response = client.get("/api/download", params={"path": "dl.txt"})
    assert response.status_code == 200
    assert response.content == b"payload"


def test_logout_clears_session(client):
    client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "supersecret123"},
    )
    client.post("/api/auth/logout")
    assert client.get("/api/files").status_code == 401
