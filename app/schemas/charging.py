from __future__ import annotations

from app.schemas.common import CamelModel


class StartOrderRequest(CamelModel):
    pile_id: str


class RealtimeOut(CamelModel):
    """与前端 RealTimeChargingData 逐字对齐；数值化传输，格式化归前端。"""

    voltage: float
    current: float
    power_kw: float
    duration_sec: float
    energy_kwh: float
    estimated_cost: float
