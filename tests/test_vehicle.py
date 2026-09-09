"""车辆信息契约测试（C 域 · Story 4）。"""

from __future__ import annotations

from tests.conftest import API, bearer

VEHICLE_KEYS = {"plateNo", "battery", "rangeKm"}


def test_vehicle_requires_auth(client):
    assert client.get(f"{API}/vehicle/current").status_code == 401


def test_vehicle_default_for_new_user(client, auth):
    """新用户无车辆记录 → 返回默认车辆（§5.5）。"""
    res = client.get(f"{API}/vehicle/current", headers=bearer(auth["token"]))
    assert res.status_code == 200, res.text
    data = res.json()
    assert set(data) == VEHICLE_KEYS
    assert data["battery"] == 75
    assert data["rangeKm"] == 260
    assert data["plateNo"] == ""


def test_vehicle_is_per_user(client, auth, make_user):
    """每个用户各自独立一条默认车辆（不串扰）。"""
    a = client.get(f"{API}/vehicle/current", headers=bearer(auth["token"])).json()
    b = client.get(f"{API}/vehicle/current", headers=bearer(make_user()["token"])).json()
    assert a == b  # 均为默认值，且彼此独立成行
