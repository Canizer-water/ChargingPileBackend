from __future__ import annotations

from tests.conftest import API, bearer
from tests.test_stations import pick_idle_pile

REALTIME_KEYS = {"voltage", "current", "powerKw", "durationSec", "energyKwh", "estimatedCost"}
ORDER_KEYS = {"id", "stationId", "stationName", "pileCode", "startTime", "endTime",
              "energyKwh", "unitPrice", "durationMin", "amount", "status"}


def test_start_requires_auth(client):
    assert client.post(f"{API}/charging/start", json={"pileId": "p000000002"}).status_code == 401


def test_start_unknown_pile_404(client, auth):
    res = client.post(f"{API}/charging/start", json={"pileId": "p-none"}, headers=bearer(auth["token"]))
    assert res.status_code == 404


def test_start_offline_pile_409(client, auth):
    res = client.post(f"{API}/charging/start", json={"pileId": "p300000001"}, headers=bearer(auth["token"]))
    assert res.status_code == 409


def test_full_charging_session(client, auth):
    headers = bearer(auth["token"])

    pile = pick_idle_pile(client, headers)
    res = client.post(f"{API}/charging/start", json={"pileId": pile["id"]}, headers=headers)
    assert res.status_code == 201, res.text
    order = res.json()
    assert set(order) == ORDER_KEYS
    assert order["status"] == "CHARGING"
    assert order["endTime"] == ""  # 进行中口径（§5.4）
    assert order["unitPrice"] == pile["pricePerKwh"]  # 单价快照
    assert order["pileCode"] == pile["code"]

    # 不变式 2：会话期间桩为 CHARGING
    assert client.get(f"{API}/piles/{pile['id']}", headers=headers).json()["status"] == "CHARGING"
    # 不变式 1：同用户第二个会话被拦
    second = pick_idle_pile(client, headers, exclude=(pile["id"],))
    res = client.post(f"{API}/charging/start", json={"pileId": second["id"]}, headers=headers)
    assert res.status_code == 409

    # 实时数据
    res = client.get(f"{API}/charging/current", headers=headers)
    assert res.status_code == 200
    snap = res.json()
    assert set(snap) == REALTIME_KEYS
    assert snap["durationSec"] >= 0
    assert snap["energyKwh"] >= 0
    assert snap["estimatedCost"] == round(snap["energyKwh"] * order["unitPrice"], 2)
    assert snap["powerKw"] > 0

    # 结束并结算
    res = client.post(f"{API}/charging/{order['id']}/stop", headers=headers)
    assert res.status_code == 200, res.text
    done = res.json()
    assert done["status"] == "FINISHED"
    assert done["endTime"] != ""
    assert done["durationMin"] >= 1
    assert done["amount"] == round(done["energyKwh"] * done["unitPrice"], 2)
    # 桩释放
    assert client.get(f"{API}/piles/{pile['id']}", headers=headers).json()["status"] == "IDLE"

    # 已结束：重复 stop 409；current 404
    assert client.post(f"{API}/charging/{order['id']}/stop", headers=headers).status_code == 409
    assert client.get(f"{API}/charging/current", headers=headers).status_code == 404


def test_stop_foreign_order_404(client, auth, make_user):
    """越权停止他人订单 → 404（不泄露存在性，§6）。"""
    headers = bearer(auth["token"])
    pile = pick_idle_pile(client, headers)
    order = client.post(f"{API}/charging/start", json={"pileId": pile["id"]}, headers=headers).json()

    other_headers = bearer(make_user()["token"])
    assert client.post(f"{API}/charging/{order['id']}/stop", headers=other_headers).status_code == 404

    # 清理本会话
    client.post(f"{API}/charging/{order['id']}/stop", headers=headers)
