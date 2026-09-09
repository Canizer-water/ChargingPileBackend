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
    assert set(body) == {"token", "refreshToken", "user"}
    assert set(body["user"]) == {"id", "username", "avatar", "createdAt"}
    assert body["user"]["username"] == phone
    assert body["user"]["id"].startswith("U")
    assert body["token"]
    assert body["refreshToken"]


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


def test_refresh_returns_new_tokens_and_rotates(client, auth):
    res = client.post(f"{API}/auth/refresh", json={"refreshToken": auth["refreshToken"]})
    assert res.status_code == 200, res.text
    body = res.json()
    assert set(body) == {"token", "refreshToken", "user"}
    assert body["user"]["id"] == auth["user"]["id"]
    # 新 access token 立即有效（用 /me 验证）
    me = client.get(f"{API}/auth/me", headers=bearer(body["token"]))
    assert me.status_code == 200
    assert me.json()["id"] == auth["user"]["id"]
    # 刷新令牌强制轮换：refreshToken 必变
    assert body["refreshToken"] != auth["refreshToken"]
    # 旧 refresh 已撤销，复用必 401
    again = client.post(f"{API}/auth/refresh", json={"refreshToken": auth["refreshToken"]})
    assert again.status_code == 401


def test_refresh_invalid_token_401(client):
    res = client.post(f"{API}/auth/refresh", json={"refreshToken": "not-a-real-token"})
    assert res.status_code == 401


def test_logout_revokes_specific_token(client, auth):
    res = client.post(f"{API}/auth/logout", json={"refreshToken": auth["refreshToken"]},
                      headers=bearer(auth["token"]))
    assert res.status_code == 200
    assert client.post(f"{API}/auth/refresh", json={"refreshToken": auth["refreshToken"]}).status_code == 401


def test_logout_without_token_revokes_all(client, make_user):
    # 同一用户两个 refresh token
    user = make_user()
    r2 = client.post(f"{API}/auth/login", json={"username": user["phone"], "password": user["password"]})
    assert r2.status_code == 200
    rt2 = r2.json()["refreshToken"]
    res = client.post(f"{API}/auth/logout", json={}, headers=bearer(user["token"]))
    assert res.status_code == 200
    assert client.post(f"{API}/auth/refresh", json={"refreshToken": rt2}).status_code == 401
    assert client.post(f"{API}/auth/refresh", json={"refreshToken": user["refreshToken"]}).status_code == 401


def test_profile_get_returns_current_user(client, auth):
    res = client.get(f"{API}/user/profile", headers=bearer(auth["token"]))
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["id"] == auth["user"]["id"]


def test_profile_requires_login(client):
    assert client.get(f"{API}/user/profile").status_code == 401


def test_profile_update_avatar(client, auth):
    res = client.put(f"{API}/user/profile", json={"avatar": "https://cdn/x.png"},
                     headers=bearer(auth["token"]))
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["avatar"] == "https://cdn/x.png"
