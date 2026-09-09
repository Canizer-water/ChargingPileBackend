from __future__ import annotations

from tests.conftest import API, bearer

STATION_KEYS = {"id", "name", "address", "latitude", "longitude", "distanceKm", "freePiles",
                "pricePerKwh", "businessHours", "piles"}
PILE_KEYS = {"id", "stationId", "code", "latitude", "longitude", "powerKw", "pricePerKwh",
             "interfaceType", "status"}


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


def test_coordinates_present_on_stations_and_piles(client, auth):
    """v0.6 地图：站点/桩均返回经纬度。"""
    headers = bearer(auth["token"])
    for st in client.get(f"{API}/stations", headers=headers).json():
        assert isinstance(st["latitude"], float) and isinstance(st["longitude"], float)
        for p in st["piles"]:
            assert isinstance(p["latitude"], float) and isinstance(p["longitude"], float)


def test_stations_nearby_filter_and_sort(client, auth):
    """给定坐标：distanceKm 服务端计算，radius 过滤，距离升序。"""
    headers = bearer(auth["token"])
    # 参考点即 s2 坐标附近 → 距离应很小、并升序
    res = client.get(f"{API}/stations", params={"lat": 34.2555, "lng": 108.9470}, headers=headers)
    assert res.status_code == 200
    stations = res.json()
    distances = [s["distanceKm"] for s in stations]
    assert distances == sorted(distances)
    # 取 s1 坐标作为参考点，radius 限制到只留非常近的站
    res = client.get(f"{API}/stations", params={"lat": 34.2600, "lng": 108.9520, "radius": 32.0},
                     headers=headers)
    assert res.status_code == 200
    assert len(res.json()) >= 1
    for s in res.json():
        assert s["distanceKm"] <= 32.0
    # 参考点远离所有站、radius=0 应返回空（距离均 > 0）
    res = client.get(f"{API}/stations", params={"lat": 34.3000, "lng": 108.9900, "radius": 0.0},
                     headers=headers)
    assert res.status_code == 200
    assert res.json() == []


def test_stations_without_coords_falls_back_to_seed_distance(client, auth):
    """未传坐标：distanceKm 回退入库值（种子值）。"""
    headers = bearer(auth["token"])
    res = client.get(f"{API}/stations", headers=headers)
    assert res.status_code == 200
    by_id = {s["id"]: s for s in res.json()}
    assert by_id["s1"]["distanceKm"] == 0.03
    assert by_id["s4"]["distanceKm"] == 2.4
