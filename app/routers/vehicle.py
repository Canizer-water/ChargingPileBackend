"""车辆端点（C 域 · Story 4）：查询/录入当前登录用户的默认车辆（设计文档 §5.7）。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.models.vehicle import Vehicle
from app.schemas.vehicle import VehicleOut, VehicleUpdate, is_valid_plate
from app.services.charging import BizError
from app.core.timeutil import utc_now

router = APIRouter(prefix="/vehicle", tags=["vehicle"])


def _new_vehicle_id() -> str:
    return f"V{uuid.uuid4().hex[:12]}"


async def _get_or_create_vehicle(db: AsyncSession, user_id: str) -> Vehicle:
    """按当前用户取车辆；无记录则落一条默认值（§5.7 懒建口径）。"""
    result = await db.execute(select(Vehicle).where(Vehicle.user_id == user_id))
    vehicle = result.scalar_one_or_none()
    if vehicle is None:
        vehicle = Vehicle(id=_new_vehicle_id(), user_id=user_id)
        db.add(vehicle)
        await db.commit()
    return vehicle


@router.get("/current", response_model=VehicleOut)
async def get_current_vehicle(db: AsyncSession = Depends(get_db),
                              user: User = Depends(get_current_user)) -> VehicleOut:
    """按当前用户查车辆；无记录则落一条默认车辆并返回（设计文档 §5.7）。"""
    vehicle = await _get_or_create_vehicle(db, user.id)
    return VehicleOut(plate_no=vehicle.plate_no, battery=vehicle.battery, range_km=vehicle.range_km)


@router.put("/current", response_model=VehicleOut)
async def update_current_vehicle(body: VehicleUpdate, db: AsyncSession = Depends(get_db),
                                 user: User = Depends(get_current_user)) -> VehicleOut:
    """写入车牌号（设计文档 §5.7）：`plateNo` 已由 schema 归一化，空串表示清除。

    校验放在 router 而非 schema，是为了让错误体保持 ``{"detail": "字符串"}``——
    前端 HTTP 层按 detail 字符串映射 toast 文案。
    """
    if not is_valid_plate(body.plate_no):
        raise BizError(422, "车牌号格式不正确")
    vehicle = await _get_or_create_vehicle(db, user.id)
    vehicle.plate_no = body.plate_no
    vehicle.updated_at = utc_now()
    await db.commit()
    return VehicleOut(plate_no=vehicle.plate_no, battery=vehicle.battery, range_km=vehicle.range_km)
