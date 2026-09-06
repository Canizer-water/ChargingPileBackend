"""站点/桩只读端点（设计文档 §5.2）。列表排序策略归前端，后端保持入库顺序。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.pile import Pile
from app.models.station import Station
from app.models.user import User
from app.schemas.station import PileOut, StationOut, station_to_out

router = APIRouter(tags=["stations"])

_NOT_FOUND_STATION = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="充电站不存在")
_NOT_FOUND_PILE = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="充电桩不存在")


@router.get("/stations", response_model=list[StationOut])
async def list_stations(db: AsyncSession = Depends(get_db),
                        _: User = Depends(get_current_user)) -> list[StationOut]:
    result = await db.execute(select(Station))
    return [station_to_out(s, s.piles) for s in result.scalars().all()]


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
    return PileOut.model_validate(pile)


@router.get("/piles/{pile_id}", response_model=PileOut)
async def get_pile(pile_id: str, db: AsyncSession = Depends(get_db),
                   _: User = Depends(get_current_user)) -> PileOut:
    pile = await db.get(Pile, pile_id)
    if pile is None:
        raise _NOT_FOUND_PILE
    return PileOut.model_validate(pile)
