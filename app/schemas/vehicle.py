"""车辆响应模型（C 域 · Story 4），与前端 Vehicle DTO 逐字对齐。"""

from __future__ import annotations

from app.schemas.common import CamelModel

#: 无车辆记录时的默认值（设计文档 §5.5）
DEFAULT_PLATE_NO = ""
DEFAULT_BATTERY = 75
DEFAULT_RANGE_KM = 260


class VehicleOut(CamelModel):
    plate_no: str
    battery: int
    range_km: int


def default_vehicle_out() -> VehicleOut:
    return VehicleOut(
        plate_no=DEFAULT_PLATE_NO,
        battery=DEFAULT_BATTERY,
        range_km=DEFAULT_RANGE_KM,
    )
