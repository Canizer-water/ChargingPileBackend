"""B1 WebSocket 实时推送 契约/行为测试（设计文档 §5.3 二期）与 B2 模拟桩上报测试。"""

from __future__ import annotations

from tests.conftest import API, bearer
from tests.test_stations import pick_idle_pile

REALTIME_KEYS = {"voltage", "current", "powerKw", "durationSec", "energyKwh", "estimatedCost"}


def _start_session(client, headers) -> dict:
    pile = pick_idle_pile(client, headers)
    res = client.post(f"{API}/charging/start", json={"pileId": pile["id"]}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _stop_session(client, headers, order_id: str) -> None:
    res = client.post(f"{API}/charging/{order_id}/stop", headers=headers)
    # 幂等清理：正常 200；已结束(409)在测试收尾阶段可接受
    assert res.status_code in (200, 409), res.text


def test_ws_rejects_session_not_found(client, auth):
    with client.websocket_connect(f"/api/v1/ws/charging/session/CO-no-such?token={auth['token']}") as ws:
        frame = ws.receive_json()
        assert frame["type"] == "error"
        assert frame["code"] == 404


def test_ws_rejects_unauthenticated(client):
    with client.websocket_connect("/api/v1/ws/charging/session/CO-none") as ws:
        frame = ws.receive_json()
        assert frame["type"] == "error"
        assert frame["code"] == 401


def test_ws_rejects_foreign_session(client, auth, make_user):
    headers = bearer(auth["token"])
    order = _start_session(client, headers)
    other = make_user()
    with client.websocket_connect(
        f"/api/v1/ws/charging/session/{order['id']}?token={other['token']}"
    ) as ws:
        frame = ws.receive_json()
        assert frame["type"] == "error"
        assert frame["code"] == 404
    _stop_session(client, headers, order["id"])


def test_ws_streams_realtime_frames_until_session_ends(client, auth):
    headers = bearer(auth["token"])
    order = _start_session(client, headers)
    try:
        with client.websocket_connect(
            f"/api/v1/ws/charging/session/{order['id']}?token={auth['token']}"
        ) as ws:
            frame = ws.receive_json()
            assert set(frame) == REALTIME_KEYS
            assert frame["powerKw"] > 0
            assert frame["estimatedCost"] >= 0

            res = client.post(f"{API}/charging/{order['id']}/stop", headers=headers)
            assert res.status_code == 200, res.text

            final = ws.receive_json()
            assert final["type"] == "session_finished"
            assert final["sessionId"] == order["id"]
    finally:
        _stop_session(client, headers, order["id"])


def test_ws_and_polling_share_same_realtime_source(client, auth):
    """B1 WS 与降级轮询 GET /charging/current 共用同一 provider（实时口径不分裂）。"""
    headers = bearer(auth["token"])
    order = _start_session(client, headers)
    try:
        with client.websocket_connect(
            f"/api/v1/ws/charging/session/{order['id']}?token={auth['token']}"
        ) as ws:
            ws_frame = ws.receive_json()
            poll = client.get(f"{API}/charging/current", headers=headers).json()
            assert set(ws_frame) == REALTIME_KEYS
            assert set(poll) == REALTIME_KEYS
            # 同一 provider、同秒取整：两路 durationSec 应一致
            assert ws_frame["durationSec"] == poll["durationSec"]
    finally:
        _stop_session(client, headers, order["id"])


def test_ws_auth_via_first_message(client, auth):
    headers = bearer(auth["token"])
    order = _start_session(client, headers)
    try:
        with client.websocket_connect(f"/api/v1/ws/charging/session/{order['id']}") as ws:
            ws.send_json({"token": auth["token"]})
            frame = ws.receive_json()
            assert set(frame) == REALTIME_KEYS
    finally:
        _stop_session(client, headers, order["id"])
