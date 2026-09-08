from __future__ import annotations

from pydantic import Field

from app.schemas.common import CamelModel


class StartOrderRequest(CamelModel):
    pile_id: str


class EstimateRequest(CamelModel):
    """费用预估请求（C 域 · Story 10）。expectedMinutes 分钟，必须为正整数。"""

    pile_id: str
    expected_minutes: int = Field(gt=0)


class EstimateOut(CamelModel):
    """预估结果：预计电量 = 功率 × 时长，费用 = 电量 × 单价（仅供参考）。"""

    pile_id: str
    unit_price: float
    power_kw: float
    expected_energy_kwh: float
    estimated_cost: float


class RealtimeOut(CamelModel):
    """与前端 RealTimeChargingData 逐字对齐；数值化传输，格式化归前端。"""

    voltage: float
    current: float
    power_kw: float
    duration_sec: float
    energy_kwh: float
    estimated_cost: float
