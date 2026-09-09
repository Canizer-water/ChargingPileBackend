"""站点/桩只读端点（设计文档 §5.2）。

`/stations` 支持可选 `lat/lng/radius`：给定坐标时服务端 haversine 计算每站 distanceKm、
按 radius(km) 附近过滤（radius 为空则不过滤）、结果距离升序；未给坐标则回退入库距离。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.pile import Pile
from app.models.station import Station
from app.models.user import User
from app.schemas.station import PileOut, StationOut, pile_to_out, station_to_out

router = APIRouter(tags=["stations"])

_NOT_FOUND_STATION = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="充电站不存在")
_NOT_FOUND_PILE = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="充电桩不存在")


@router.get("/stations", response_model=list[StationOut])
async def list_stations(db: AsyncSession = Depends(get_db),
                        _: User = Depends(get_current_user),
                        lat: float | None = Query(default=None),
                        lng: float | None = Query(default=None),
                        radius: float | None = Query(default=None)) -> list[StationOut]:
    result = await db.execute(select(Station))
    stations = result.scalars().all()
    have_ref = lat is not None and lng is not None
    # distanceKm：有参考坐标则实时计算（用于附近过滤与排序），否则用入库值
    items = [
        (station_to_out(s, s.piles, ref_lat=lat, ref_lng=lng),
         s.distance_km if not have_ref else None)
        for s in stations
    ]
    distance_key = lambda item: item[0].distance_km if have_ref else item[1] or 0.0
    if have_ref and radius is not None:
        items = [(out, _) for out, _ in items if out.distance_km <= radius]
    items.sort(key=distance_key)
    return [out for out, _ in items]


@router.get("/stations/{station_id}", response_model=StationOut)
async def get_station(station_id: str, db: AsyncSession = Depends(get_db),
                      _: User = Depends(get_current_user)) -> StationOut:
    station = await db.get(Station, station_id)
    if station is None:
        raise _NOT_FOUND_STATION
    return station_to_out(station, station.piles)


@router.get("/piles/by-code/{code}", response_model=PileOut)
async def get_pile_by_code(code: str, db: AsyncSession = Depends(get_db),
                           _: User = Depends(get_current_user)) -> PileOut:
    """扫码解析入口：二维码内容为桩编号 code。"""
    result = await db.execute(select(Pile).where(Pile.code == code))
    pile = result.scalar_one_or_none()
    if pile is None:
        raise _NOT_FOUND_PILE
    return pile_to_out(pile)


@router.get("/piles/{pile_id}", response_model=PileOut)
async def get_pile(pile_id: str, db: AsyncSession = Depends(get_db),
                   _: User = Depends(get_current_user)) -> PileOut:
    pile = await db.get(Pile, pile_id)
    if pile is None:
        raise _NOT_FOUND_PILE
    return pile_to_out(pile)
