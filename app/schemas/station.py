from __future__ import annotations

from typing import Literal

from app.schemas.common import CamelModel

PileStatusLiteral = Literal["IDLE", "CHARGING", "OFFLINE", "FAULT"]


class PileOut(CamelModel):
    id: str
    station_id: str
    code: str
    latitude: float
    longitude: float
    power_kw: float
    price_per_kwh: float
    interface_type: str
    status: PileStatusLiteral


class StationOut(CamelModel):
    id: str
    name: str
    address: str
    latitude: float
    longitude: float
    distance_km: float
    free_piles: int
    price_per_kwh: float
    business_hours: str
    piles: list[PileOut]


def pile_to_out(pile) -> PileOut:
    """ORM Pile → PileOut（lat/lng → latitude/longitude，做显式映射）。"""
    return PileOut(
        id=pile.id,
        station_id=pile.station_id,
        code=pile.code,
        latitude=pile.lat,
        longitude=pile.lng,
        power_kw=pile.power_kw,
        price_per_kwh=pile.price_per_kwh,
        interface_type=pile.interface_type,
        status=pile.status,
    )


def station_to_out(station, piles: list, ref_lat: float | None = None,
                   ref_lng: float | None = None) -> StationOut:
    """由 ORM Station + 已加载 piles 组装响应。

    - freePiles 为 IDLE 聚合（不入库派生）。
    - distanceKm：提供 ref_lat/ref_lng 时按站点坐标 haversine 实时计算；否则回退入库 distance_km。
    """
    from app.services.geo import haversine_km

    pile_outs = [pile_to_out(p) for p in piles]
    if ref_lat is not None and ref_lng is not None:
        distance_km = round(haversine_km(ref_lat, ref_lng, station.lat, station.lng), 3)
    else:
        distance_km = station.distance_km
    return StationOut(
        id=station.id,
        name=station.name,
        address=station.address,
        latitude=station.lat,
        longitude=station.lng,
        distance_km=distance_km,
        free_piles=sum(1 for p in pile_outs if p.status == "IDLE"),
        price_per_kwh=station.price_per_kwh,
        business_hours=station.business_hours,
        piles=pile_outs,
    )
