"""Снимает скриншот интерфейса файлового менеджера через Chrome DevTools Protocol.

Авторизуется в API, подставляет cookie сессии и фотографирует страницу.
Запуск: python tools/screenshot.py [url] [output.png]
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
OUTPUT = Path(sys.argv[2] if len(sys.argv) > 2 else "design-check.png").resolve()
USERNAME = os.environ.get("FM_USER", "admin")
PASSWORD = os.environ["FM_PASSWORD"]

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]


def find_browser() -> str:
    for path in CHROME_CANDIDATES:
        if Path(path).is_file():
            return path
    raise SystemExit("Chrome/Edge не найден")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def login() -> str:
    """Возвращает значение cookie сессии."""
    payload = json.dumps({"username": USERNAME, "password": PASSWORD}).encode()
    request = urllib.request.Request(
        f"{BASE_URL}/api/auth/login",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        cookie_header = response.headers.get("Set-Cookie", "")
    token = cookie_header.split(";")[0]
    if not token.startswith("fm_session="):
        raise SystemExit(f"не удалось получить cookie: {cookie_header!r}")
    return token.split("=", 1)[1]


def cdp(ws_url: str, method: str, params: dict | None = None, *, timeout: float = 30):
    """Минимальный клиент CDP поверх WebSocket (без внешних зависимостей)."""
    import ssl  # noqa: F401  (нужен для совместимости окружений)
    from websocket import create_connection  # type: ignore

    connection = create_connection(ws_url, timeout=timeout)
    try:
        connection.send(json.dumps({"id": 1, "method": method, "params": params or {}}))
        while True:
            message = json.loads(connection.recv())
            if message.get("id") == 1:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message.get("result", {})
    finally:
        connection.close()


def main() -> None:
    browser = find_browser()
    port = free_port()
    profile = Path(tempfile.mkdtemp(prefix="fm-chrome-"))

    process = subprocess.Popen(
        [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--hide-scrollbars",
            f"--user-data-dir={profile}",
            f"--remote-debugging-port={port}",
            "--remote-allow-origins=*",
            "--window-size=1354,904",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        # Ждём поднятия DevTools.
        endpoint = f"http://127.0.0.1:{port}/json/version"
        for _ in range(50):
            try:
                with urllib.request.urlopen(endpoint, timeout=1) as response:
                    json.load(response)
                break
            except Exception:
                time.sleep(0.2)
        else:
            raise SystemExit("Chrome не поднял порт отладки")

        token = login()
        print(f"cookie получена, длина токена: {len(token)}")

        # Создаём вкладку.
        new_tab = urllib.request.Request(
            f"http://127.0.0.1:{port}/json/new?{BASE_URL}",
            method="PUT",
        )
        with urllib.request.urlopen(new_tab, timeout=10) as response:
            tab = json.load(response)
        ws_url = tab["webSocketDebuggerUrl"]

        cdp(ws_url, "Network.enable")
        cdp(ws_url, "Page.enable")
        cdp(
            ws_url,
            "Network.setCookie",
            {
                "name": "fm_session",
                "value": token,
                "domain": "localhost",
                "path": "/",
            },
        )
        cdp(ws_url, "Emulation.setDeviceMetricsOverride",
            {"width": 1354, "height": 904, "deviceScaleFactor": 2, "mobile": False})
        cdp(ws_url, "Page.navigate", {"url": BASE_URL})
        time.sleep(3.5)  # даём React отрисоваться и загрузить список файлов

        shot = cdp(ws_url, "Page.captureScreenshot", {"format": "png"})
        OUTPUT.write_bytes(base64.b64decode(shot["data"]))
        print(f"Скриншот сохранён: {OUTPUT} ({OUTPUT.stat().st_size} байт)")
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    main()
