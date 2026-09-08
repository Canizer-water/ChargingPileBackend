"""测试环境：临时 SQLite + TestClient（导入 app 前必须先设环境变量）。"""

from __future__ import annotations

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="chargingpile-test-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{os.path.join(_TMP, 'test.db').replace(os.sep, '/')}"
os.environ["SECRET_KEY"] = "unit-test-secret-0123456789abcdef0123456789abcdef"  # ≥32B，避免 HS256 短密钥告警
os.environ["REALTIME_SOURCE"] = "sim"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

API = "/api/v1"


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


_counter = {"phone": 13800000000}


def _next_phone() -> str:
    _counter["phone"] += 1
    return str(_counter["phone"])


def _register_or_login(client, phone: str, password: str = "pwd-123456") -> dict:
    res = client.post(f"{API}/auth/register", json={"username": phone, "password": password})
    if res.status_code == 409:
        res = client.post(f"{API}/auth/login", json={"username": phone, "password": password})
    assert res.status_code in (200, 201), res.text
    data = res.json()
    return {"token": data["token"], "refreshToken": data["refreshToken"],
            "user": data["user"], "phone": phone, "password": password}


@pytest.fixture
def phone() -> str:
    """每个测试独立手机号，避免跨用例的账号/会话串扰。"""
    return _next_phone()


@pytest.fixture
def auth(client, phone) -> dict:
    """注册（或登录）主测试用户。"""
    return _register_or_login(client, phone)


@pytest.fixture
def make_user(client):
    """按需注册额外用户（跨模块计数唯一，勿再手动拼手机号）。"""
    def _factory() -> dict:
        return _register_or_login(client, _next_phone())
    return _factory


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
