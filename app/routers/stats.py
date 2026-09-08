"""每日充电统计端点：GET /stats/daily（设计文档 §5.5，Story 12）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.common import Envelope, ok
from app.schemas.stat import DailyStatsOut
from app.services.stats import list_daily_stats

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/daily", response_model=Envelope[list[DailyStatsOut]])
async def daily(days: int = 7, db: AsyncSession = Depends(get_db),
                user: User = Depends(get_current_user)) -> Envelope[list[DailyStatsOut]]:
    return ok(await list_daily_stats(db, user.id, days))
