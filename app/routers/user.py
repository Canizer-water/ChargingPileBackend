"""用户端点：偏好 settings（D 域，§5.5）＋ 个人档案 profile（A 域，§5.1.1，Story 16）。

统一使用 Envelope 响应（设计文档 §5.6）。username 为登录凭证（11 位手机号、全局唯一）
——不可修改；PUT /profile 仅允许更新展示字段。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.common import Envelope, ok
from app.schemas.user import (
    ProfileUpdateRequest,
    UserOut,
    UserSettingsOut,
    UserSettingsUpdate,
)
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


@router.get("/profile", response_model=Envelope[UserOut])
async def get_profile(current: User = Depends(get_current_user)) -> Envelope[UserOut]:
    return ok(UserOut.model_validate(current))


@router.put("/profile", response_model=Envelope[UserOut])
async def update_profile(body: ProfileUpdateRequest, db: AsyncSession = Depends(get_db),
                         current: User = Depends(get_current_user)) -> Envelope[UserOut]:
    if body.avatar is not None:
        current.avatar = body.avatar.strip()
    await db.commit()
    await db.refresh(current)
    return ok(UserOut.model_validate(current))
