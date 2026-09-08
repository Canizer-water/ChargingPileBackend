"""用户档案端点：GET/PUT /profile（设计文档 §5.1.1，Story 16）。

username 为登录凭证（11 位手机号、全局唯一）——不可修改；PUT 仅允许更新展示字段。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.user import ProfileUpdateRequest, UserOut

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/profile", response_model=UserOut)
async def get_profile(current: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current)


@router.put("/profile", response_model=UserOut)
async def update_profile(body: ProfileUpdateRequest, db: AsyncSession = Depends(get_db),
                         current: User = Depends(get_current_user)) -> UserOut:
    if body.avatar is not None:
        current.avatar = body.avatar.strip()
    await db.commit()
    await db.refresh(current)
    return UserOut.model_validate(current)
