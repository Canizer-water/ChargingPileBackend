"""车辆端点（C 域 · Story 4）：查询当前登录用户的默认车辆。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.models.vehicle import Vehicle
from app.schemas.vehicle import VehicleOut

router = APIRouter(prefix="/vehicle", tags=["vehicle"])


def _new_vehicle_id() -> str:
    return f"V{uuid.uuid4().hex[:12]}"


@router.get("/current", response_model=VehicleOut)
async def get_current_vehicle(db: AsyncSession = Depends(get_db),
                              user: User = Depends(get_current_user)) -> VehicleOut:
    """按当前用户查车辆；无记录则落一条默认车辆并返回（设计文档 §5.5）。"""
    result = await db.execute(select(Vehicle).where(Vehicle.user_id == user.id))
    vehicle = result.scalar_one_or_none()
    if vehicle is None:
        vehicle = Vehicle(id=_new_vehicle_id(), user_id=user.id)
        db.add(vehicle)
        await db.commit()
    return VehicleOut(plate_no=vehicle.plate_no, battery=vehicle.battery, range_km=vehicle.range_km)
