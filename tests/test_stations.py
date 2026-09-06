from __future__ import annotations

from tests.conftest import API, bearer

STATION_KEYS = {"id", "name", "address", "distanceKm", "freePiles",
                "pricePerKwh", "businessHours", "piles"}
PILE_KEYS = {"id", "stationId", "code", "powerKw", "pricePerKwh", "interfaceType", "status"}


def pick_idle_pile(client, headers, exclude=()):
    """从当前库内挑一个空闲桩（跨用例状态无关）。"""
    for st in client.get(f"{API}/stations", headers=headers).json():
        for pile in st["piles"]:
            if pile["status"] == "IDLE" and pile["id"] not in exclude:
                return pile
    raise AssertionError("库中没有空闲桩")


def test_stations_requires_auth(client):
    assert client.get(f"{API}/stations").status_code == 401


def test_stations_list_shape_and_free_piles_aggregate(client, auth):
    res = client.get(f"{API}/stations", headers=bearer(auth["token"]))
    assert res.status_code == 200
    stations = res.json()
    assert len(stations) == 4
    for st in stations:
        assert set(st) == STATION_KEYS
        idle = sum(1 for p in st["piles"] if p["status"] == "IDLE")
        assert st["freePiles"] == idle  # 派生不变式
        for p in st["piles"]:
            assert set(p) == PILE_KEYS


def test_station_detail_and_404(client, auth):
    headers = bearer(auth["token"])
    res = client.get(f"{API}/stations/s1", headers=headers)
    assert res.status_code == 200
    assert res.json()["name"] == "诺得充电中心"
    assert client.get(f"{API}/stations/nope", headers=headers).status_code == 404


def test_pile_by_code_and_status(client, auth):
    headers = bearer(auth["token"])
    res = client.get(f"{API}/piles/by-code/p300000001", headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "OFFLINE"  # 种子保留离线桩
    assert client.get(f"{API}/piles/by-code/pXXXXXX", headers=headers).status_code == 404
    assert client.get(f"{API}/piles/p000000002", headers=headers).status_code == 200
    assert client.get(f"{API}/piles/no-such", headers=headers).status_code == 404
