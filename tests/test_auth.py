from __future__ import annotations

from tests.conftest import API, bearer


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_register_success_camel_and_no_password(client, phone):
    res = client.post(f"{API}/auth/register", json={"username": phone, "password": "pwd-123456"})
    assert res.status_code == 201, res.text
    body = res.json()
    assert set(body) == {"token", "user"}
    assert set(body["user"]) == {"id", "username", "avatar", "createdAt"}
    assert body["user"]["username"] == phone
    assert body["user"]["id"].startswith("U")
    assert body["token"]


def test_register_duplicate_username_409(client, auth, phone):
    res = client.post(f"{API}/auth/register", json={"username": phone, "password": "pwd-654321"})
    assert res.status_code == 409
    assert "已注册" in res.json()["detail"]


def test_register_invalid_input_422(client):
    # 非 11 位手机号
    res = client.post(f"{API}/auth/register", json={"username": "123", "password": "pwd-123456"})
    assert res.status_code == 422
    # 密码过短（对齐前端 6-20 口径）
    res = client.post(f"{API}/auth/register", json={"username": "13911112222", "password": "123"})
    assert res.status_code == 422


def test_login_wrong_password_401(client, auth, phone):
    res = client.post(f"{API}/auth/login", json={"username": phone, "password": "wrong-pass"})
    assert res.status_code == 401


def test_login_unknown_user_401(client):
    res = client.post(f"{API}/auth/login", json={"username": "13777778888", "password": "whatever"})
    assert res.status_code == 401


def test_login_success(client, auth, phone):
    res = client.post(f"{API}/auth/login", json={"username": phone, "password": auth["password"]})
    assert res.status_code == 200
    assert res.json()["user"]["id"] == auth["user"]["id"]
    assert res.json()["token"]


def test_me_requires_valid_token(client, auth):
    assert client.get(f"{API}/auth/me").status_code == 401
    assert client.get(f"{API}/auth/me", headers=bearer("not-a-jwt")).status_code == 401
    res = client.get(f"{API}/auth/me", headers=bearer(auth["token"]))
    assert res.status_code == 200
    assert res.json()["username"] == auth["phone"]
