"""每日充电统计聚合（设计文档 §5.5 / §11 Story 12）。"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import utc_now
from app.models.daily_stat import DailyChargingStat
from app.schemas.stat import DailyStatsOut


async def list_daily_stats(db: AsyncSession, user_id: str, days: int = 7) -> list[DailyStatsOut]:
    """近 N 天（含当天）统计，缺数据日期零填充，便于前端趋势图直接渲染。"""
    days = max(1, min(int(days), 30))
    today = utc_now().date()
    start = today - timedelta(days=days - 1)

    result = await db.execute(
        select(DailyChargingStat)
        .where(
            DailyChargingStat.user_id == user_id,
            DailyChargingStat.date >= start.isoformat(),
            DailyChargingStat.date <= today.isoformat(),
        )
        .order_by(DailyChargingStat.date)
    )
    rows = {r.date: r for r in result.scalars().all()}

    out: list[DailyStatsOut] = []
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        row = rows.get(d)
        out.append(DailyStatsOut(
            date=d,
            total_energy_kwh=round(row.total_energy_kwh, 2) if row else 0.0,
            total_amount=round(row.total_amount, 2) if row else 0.0,
            order_count=row.order_count if row else 0,
        ))
    return out
