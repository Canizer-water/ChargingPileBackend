"""B2 独立模拟桩 REST 上报契约/行为测试。"""

from __future__ import annotations

import pytest

from tests.conftest import API, bearer
from tests.test_stations import pick_idle_pile
from app.services.simulator import registry


@pytest.fixture(autouse=True)
def _clean_simulator_registry():
    """进程级注册表跨用例隔离：每测后用后清理，避免绑定桩残留影响其他业务测试。"""
    yield
    registry.clear()


def test_simulator_register_heartbeat_telemetry_done(client, auth):
    """模拟桩完整链路：register → heartbeat/telemetry → done（后端经 charging.py 结算）。"""
    headers = bearer(auth["token"])
    pile = pick_idle_pile(client, headers)

    res = client.post(
        f"{API}/simulator/register",
        json={"deviceId": "dev-p000000002", "pileCode": pile["code"]},
    )
    assert res.status_code == 200, res.text
    reg = res.json()
    assert reg["pileCode"] == pile["code"]
    assert reg["pileStatus"] == pile["status"]  # IDLE
    assert reg["heartbeatIntervalSec"] > 0
    sim_id = reg["simulatorId"]

    # 心跳与遥测（遥测回执带库内权威桩状态）
    hb = client.post(f"{API}/simulator/{sim_id}/heartbeat").json()
    assert hb["pileStatus"] == "IDLE"
    assert hb["online"] is True

    order = client.post(f"{API}/charging/start", json={"pileId": pile["id"]}, headers=headers)
    assert order.status_code == 201, order.text
    order_id = order.json()["id"]

    tel = client.post(
        f"{API}/simulator/{sim_id}/telemetry",
        json={"voltage": 720, "current": 100, "powerKw": 72.0, "energyKwh": 0.5},
    )
    assert tel.status_code == 200, tel.text
    assert tel.json()["pileStatus"] == "CHARGING"

    # done → 后端结算订单、桩回 IDLE（裁决在 services/charging.py）
    done = client.post(f"{API}/simulator/{sim_id}/done")
    assert done.status_code == 200, done.text
    assert done.json()["settledOrderId"] == order_id
    assert done.json()["pileStatus"] == "IDLE"
    assert client.get(f"{API}/orders/{order_id}", headers=headers).json()["status"] == "FINISHED"

    # 重复 done（桩已空闲）幂等：无待结算订单
    again = client.post(f"{API}/simulator/{sim_id}/done").json()
    assert again["settledOrderId"] == ""


def test_simulator_unknown_device_404(client):
    assert client.post(f"{API}/simulator/SIM-nope/heartbeat").status_code == 404
    assert client.post(
        f"{API}/simulator/SIM-nope/telemetry",
        json={"voltage": 0, "current": 0, "powerKw": 0, "energyKwh": 0},
    ).status_code == 404
    assert client.post(f"{API}/simulator/SIM-nope/done").status_code == 404


def test_simulator_register_unknown_pile_404(client):
    res = client.post(
        f"{API}/simulator/register",
        json={"deviceId": "dev-x", "pileCode": "CODE-NO-SUCH"},
    )
    assert res.status_code == 404


def test_simulator_register_idempotent_and_pile_conflict(client):
    res = client.post(
        f"{API}/simulator/register",
        json={"deviceId": "dev-same", "pileCode": "p000000003"},
    )
    assert res.status_code == 200
    sim_id = res.json()["simulatorId"]

    again = client.post(
        f"{API}/simulator/register",
        json={"deviceId": "dev-same", "pileCode": "p000000003"},
    )
    assert again.status_code == 200
    assert again.json()["simulatorId"] == sim_id

    conflict = client.post(
        f"{API}/simulator/register",
        json={"deviceId": "dev-other", "pileCode": "p000000003"},
    )
    assert conflict.status_code == 409


def test_simulator_device_can_rebind_to_another_pile(client):
    res = client.post(
        f"{API}/simulator/register",
        json={"deviceId": "dev-move", "pileCode": "p000000002"},
    )
    assert res.status_code == 200
    sim_id = res.json()["simulatorId"]

    moved = client.post(
        f"{API}/simulator/register",
        json={"deviceId": "dev-move", "pileCode": "p000000003"},
    )
    assert moved.status_code == 200
    assert moved.json()["simulatorId"] == sim_id
    assert moved.json()["pileCode"] == "p000000003"

    # 旧桩释放：新设备可再注册 p000000002
    fresh = client.post(
        f"{API}/simulator/register",
        json={"deviceId": "dev-new", "pileCode": "p000000002"},
    )
    assert fresh.status_code == 200
