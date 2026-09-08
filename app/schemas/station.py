from __future__ import annotations

from typing import Literal

from app.schemas.common import CamelModel

PileStatusLiteral = Literal["IDLE", "CHARGING", "OFFLINE", "FAULT"]


class PileOut(CamelModel):
    id: str
    station_id: str
    code: str
    power_kw: float
    price_per_kwh: float
    interface_type: str
    status: PileStatusLiteral


class StationOut(CamelModel):
    id: str
    name: str
    address: str
    distance_km: float
    free_piles: int
    price_per_kwh: float
    business_hours: str
    piles: list[PileOut]


def station_to_out(station, piles: list) -> StationOut:
    """由 ORM Station + 已加载 piles 组装响应；freePiles 为 IDLE 聚合。"""
    pile_outs = [PileOut.model_validate(p) for p in piles]
    return StationOut(
        id=station.id,
        name=station.name,
        address=station.address,
        distance_km=station.distance_km,
        free_piles=sum(1 for p in pile_outs if p.status == "IDLE"),
        price_per_kwh=station.price_per_kwh,
        business_hours=station.business_hours,
        piles=pile_outs,
    )
