"""车辆信息契约测试（C 域 · Story 4）：查询 + 车牌录入（设计文档 §5.7）。"""

from __future__ import annotations

from tests.conftest import API, bearer

VEHICLE_KEYS = {"plateNo", "battery", "rangeKm"}


def test_vehicle_requires_auth(client):
    assert client.get(f"{API}/vehicle/current").status_code == 401


def test_vehicle_default_for_new_user(client, auth):
    """新用户无车辆记录 → 返回默认车辆（§5.7）。"""
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


# --------------------------------------------------------------------------- #
# PUT /vehicle/current —— 车牌录入（v0.9）
# --------------------------------------------------------------------------- #

def test_update_plate_requires_auth(client):
    assert client.put(f"{API}/vehicle/current", json={"plateNo": "陕A12345"}).status_code == 401


def test_update_plate_persists_and_returns_shape(client, auth):
    """写入后 GET 反映新值；响应形状仍为 VehicleOut（不含多余字段）。"""
    res = client.put(f"{API}/vehicle/current", json={"plateNo": "陕A12345"}, headers=bearer(auth["token"]))
    assert res.status_code == 200, res.text
    assert set(res.json()) == VEHICLE_KEYS
    assert res.json()["plateNo"] == "陕A12345"
    assert client.get(f"{API}/vehicle/current", headers=bearer(auth["token"])).json()["plateNo"] == "陕A12345"


def test_update_plate_lazy_creates_row(client, auth):
    """新用户未经 GET 直接 PUT 也应懒建成功。"""
    res = client.put(f"{API}/vehicle/current", json={"plateNo": "京A88888"}, headers=bearer(auth["token"]))
    assert res.status_code == 200, res.text
    assert res.json()["plateNo"] == "京A88888"


def test_update_plate_normalized(client, auth):
    """识别结果常见脏格式（空格/圆点/小写）归一化后入库，避免同牌多写法（§5.7）。"""
    res = client.put(f"{API}/vehicle/current", json={"plateNo": " 陕a · 1 2 3 4 5 "},
                     headers=bearer(auth["token"]))
    assert res.status_code == 200, res.text
    assert res.json()["plateNo"] == "陕A12345"


def test_update_plate_rejects_bad_format(client, auth):
    """过短 / 含非法字符 → 422，且 detail 为可读字符串（前端按此弹 toast）。"""
    for bad in ("A1", "!!", "x" * 20):
        res = client.put(f"{API}/vehicle/current", json={"plateNo": bad}, headers=bearer(auth["token"]))
        assert res.status_code == 422, f"{bad!r} 应被拒绝：{res.text}"
        assert res.json()["detail"] == "车牌号格式不正确"


def test_update_plate_empty_clears(client, auth):
    """空串表示清除车牌（用户删掉录入值的路径），不是校验失败。"""
    headers = bearer(auth["token"])
    client.put(f"{API}/vehicle/current", json={"plateNo": "浙B2K109"}, headers=headers)
    res = client.put(f"{API}/vehicle/current", json={"plateNo": ""}, headers=headers)
    assert res.status_code == 200, res.text
    assert res.json()["plateNo"] == ""


def test_update_plate_is_per_user(client, auth, make_user):
    """改车牌只影响本人车辆，不串扰他人。"""
    other = bearer(make_user()["token"])
    client.put(f"{API}/vehicle/current", json={"plateNo": "粤B66666"}, headers=bearer(auth["token"]))
    assert client.get(f"{API}/vehicle/current", headers=other).json()["plateNo"] == ""


def test_update_plate_leaves_battery_untouched(client, auth):
    """battery/rangeKm 不可由端侧修改（§5.7）：请求体带多余字段也不生效。"""
    res = client.put(f"{API}/vehicle/current",
                     json={"plateNo": "川A12345", "battery": 1, "rangeKm": 2},
                     headers=bearer(auth["token"]))
    assert res.status_code == 200, res.text
    assert res.json()["battery"] == 75
    assert res.json()["rangeKm"] == 260
