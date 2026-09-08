"""D 域（刘薇·feat/d-orders）功能测试：Envelope / scan / settings / stats / 分页 / 自动断电。

覆盖设计文档 §5.5/§5.6 与 §7.1；旧接口保持原形状由各自测试文件负责。
"""

from __future__ import annotations

import time

from tests.conftest import API, bearer
from tests.test_orders import _finish_one_session
from tests.test_stations import pick_idle_pile

ENVELOPE_KEYS = {"success", "errorCode", "message", "data"}
PILE_KEYS = {"id", "stationId", "code", "powerKw", "pricePerKwh", "interfaceType", "status"}
SETTINGS_KEYS = {"autoStop", "stopEnergyKwh", "stopThreshold"}
STAT_KEYS = {"date", "totalEnergyKwh", "totalAmount", "orderCount"}
ORDER_PAGE_KEYS = {"items", "page", "size", "total"}


def test_scan_resolve_envelope(client, auth):
    headers = bearer(auth["token"])
    res = client.post(f"{API}/scan/resolve", json={"code": "p000000002"}, headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert set(body) == ENVELOPE_KEYS
    assert body["success"] is True and body["errorCode"] == 0 and body["message"] == "ok"
    assert set(body["data"]) == PILE_KEYS
    assert body["data"]["code"] == "p000000002"

    # 桩不存在 → 走全局 {"detail"} 404（不包 Envelope，保持前端映射兼容）
    res = client.post(f"{API}/scan/resolve", json={"code": "pXXXXXX"}, headers=headers)
    assert res.status_code == 404
    assert "detail" in res.json()

    # 需登录
    assert client.post(f"{API}/scan/resolve", json={"code": "p000000002"}).status_code == 401


def test_user_settings_get_update(client, auth):
    res = client.get(f"{API}/user/settings", headers=bearer(auth["token"]))
    assert res.status_code == 200
    d = res.json()["data"]
    assert set(d) == SETTINGS_KEYS
    assert d["autoStop"] is False
    assert d["stopThreshold"] == 90.0

    res = client.put(f"{API}/user/settings", json={"autoStop": True, "stopEnergyKwh": 5.5, "stopThreshold": 80},
                     headers=bearer(auth["token"]))
    d = res.json()["data"]
    assert d["autoStop"] is True and d["stopEnergyKwh"] == 5.5 and d["stopThreshold"] == 80

    # 局部更新：只改能量阈值，autoStop 保持 True
    res = client.put(f"{API}/user/settings", json={"stopEnergyKwh": 3}, headers=bearer(auth["token"]))
    d = res.json()["data"]
    assert d["autoStop"] is True and d["stopEnergyKwh"] == 3

    # 需登录
    assert client.get(f"{API}/user/settings").status_code == 401


def test_orders_pagination_and_status_filter(client, auth):
    headers = bearer(auth["token"])
    id1 = _finish_one_session(client, headers)["id"]
    id2 = _finish_one_session(client, headers)["id"]

    res = client.get(f"{API}/orders?page=1&size=10", headers=headers)
    assert res.status_code == 200
    page = res.json()["data"]
    assert set(page) == ORDER_PAGE_KEYS
    assert page["total"] == 2 and page["page"] == 1 and page["size"] == 10
    assert [o["id"] for o in page["items"]] == [id2, id1]  # 新单在前

    # 状态过滤：FINISHED 命中全部，CHARGING 命中 0
    assert client.get(f"{API}/orders?status=FINISHED", headers=headers).json()["data"]["total"] == 2
    assert client.get(f"{API}/orders?status=CHARGING", headers=headers).json()["data"]["total"] == 0

    # 非法 status → 422；超出 size 上限 → 422；未登录 → 401
    assert client.get(f"{API}/orders?status=BAD", headers=headers).status_code == 422
    assert client.get(f"{API}/orders?size=51", headers=headers).status_code == 422
    assert client.get(f"{API}/orders").status_code == 401


def test_daily_stats_zero_fill_and_accumulate(client, auth):
    headers = bearer(auth["token"])
    done = _finish_one_session(client, headers)

    res = client.get(f"{API}/stats/daily?days=7", headers=headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert len(data) == 7
    assert set(data[0]) == STAT_KEYS
    assert data[0]["totalEnergyKwh"] == 0.0 and data[0]["orderCount"] == 0  # 零填充

    today = data[-1]
    assert today["orderCount"] == 1
    assert today["totalEnergyKwh"] == round(done["energyKwh"], 2)
    assert today["totalAmount"] == round(done["amount"], 2)

    # 未登录 401
    assert client.get(f"{API}/stats/daily").status_code == 401


def test_auto_stop_setting_ends_session(client, auth):
    headers = bearer(auth["token"])
    res = client.put(f"{API}/user/settings", json={"autoStop": True, "stopEnergyKwh": 0.01},
                     headers=headers)
    assert res.status_code == 200
    assert res.json()["data"]["autoStop"] is True

    pile = pick_idle_pile(client, headers)
    order = client.post(f"{API}/charging/start", json={"pileId": pile["id"]}, headers=headers).json()
    time.sleep(0.6)  # 让模拟能量超过 0.01 kWh 阈值

    # 自动断电结算 → current 回到 404（会话已结束）
    assert client.get(f"{API}/charging/current", headers=headers).status_code == 404
    orders = client.get(f"{API}/orders", headers=headers).json()["data"]["items"]
    assert orders[0]["id"] == order["id"]
    assert orders[0]["status"] == "FINISHED"
    assert client.get(f"{API}/piles/{pile['id']}", headers=headers).json()["status"] == "IDLE"

    # 复位偏好，避免影响后续用例
    client.put(f"{API}/user/settings", json={"autoStop": False}, headers=headers)
