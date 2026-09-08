"""用户偏好端点：GET/PUT /user/settings（设计文档 §5.5，Story 11）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.common import Envelope, ok
from app.schemas.user import UserSettingsOut, UserSettingsUpdate
from app.services.charging import get_or_create_settings, set_settings

router = APIRouter(prefix="/user", tags=["user"])


def _to_out(row) -> UserSettingsOut:
    return UserSettingsOut(
        auto_stop=row.auto_stop,
        stop_energy_kwh=row.stop_energy_kwh,
        stop_threshold=row.stop_threshold,
    )


@router.get("/settings", response_model=Envelope[UserSettingsOut])
async def get_settings(db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)) -> Envelope[UserSettingsOut]:
    return ok(_to_out(await get_or_create_settings(db, user.id)))


@router.put("/settings", response_model=Envelope[UserSettingsOut])
async def update_settings(body: UserSettingsUpdate, db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user)) -> Envelope[UserSettingsOut]:
    row = await set_settings(db, user.id, body.auto_stop, body.stop_energy_kwh, body.stop_threshold)
    return ok(_to_out(row))
