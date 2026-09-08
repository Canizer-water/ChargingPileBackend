from __future__ import annotations

from app.schemas.common import CamelModel


class DailyStatsOut(CamelModel):
    """每日充电统计（设计文档 §5.5）。与前端 Types.ets: DailyChargeStat 对齐。"""

    date: str
    total_energy_kwh: float
    total_amount: float
    order_count: int
