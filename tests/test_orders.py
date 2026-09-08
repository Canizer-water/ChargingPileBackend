from __future__ import annotations

from tests.conftest import API, bearer
from tests.test_stations import pick_idle_pile


def _finish_one_session(client, headers):
    pile = pick_idle_pile(client, headers)
    order = client.post(f"{API}/charging/start", json={"pileId": pile["id"]}, headers=headers).json()
    return client.post(f"{API}/charging/{order['id']}/stop", headers=headers).json()


def test_orders_isolated_per_user(client, auth, make_user):
    headers = bearer(auth["token"])
    done = _finish_one_session(client, headers)

    res = client.get(f"{API}/orders", headers=headers)
    assert res.status_code == 200
    page = res.json()["data"]
    assert page["total"] == 1
    assert page["page"] == 1 and page["size"] == 10
    assert page["items"][0]["id"] == done["id"]

    # 新用户看不到别人的订单
    other_headers = bearer(make_user()["token"])
    assert client.get(f"{API}/orders", headers=other_headers).json()["data"]["total"] == 0
    assert client.get(f"{API}/orders/{done['id']}", headers=other_headers).status_code == 404


def test_orders_list_newest_first(client, auth):
    headers = bearer(auth["token"])
    first = _finish_one_session(client, headers)
    second = _finish_one_session(client, headers)
    ids = [o["id"] for o in client.get(f"{API}/orders", headers=headers).json()["data"]["items"]]
    assert ids[0] == second["id"]
    assert first["id"] in ids
    assert len(ids) == len(set(ids))  # 订单号无碰撞


def test_order_detail_matches_list(client, auth):
    headers = bearer(auth["token"])
    done = _finish_one_session(client, headers)
    res = client.get(f"{API}/orders/{done['id']}", headers=headers)
    assert res.status_code == 200
    assert res.json() == done
    assert client.get(f"{API}/orders/CO-not-exist", headers=headers).status_code == 404
