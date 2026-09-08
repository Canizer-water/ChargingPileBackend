"""认证端点：register / login / refresh / logout / me（设计文档 §5.1）。"""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_user, get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.core.timeutil import utc_now
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.user import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResult,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_INVALID_TOKEN = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="登录状态已失效或已过期",
)


def _new_user_id() -> str:
    return f"U{uuid.uuid4().hex[:12]}"


async def _issue_tokens(db: AsyncSession, user: User) -> TokenResult:
    """签发 access + refresh，并把 refresh 落库（供撤销/轮换）。"""
    settings = get_settings()
    refresh = create_refresh_token()
    db.add(RefreshToken(
        token=refresh,
        user_id=user.id,
        expires_at=utc_now() + timedelta(days=settings.refresh_token_expire_days),
    ))
    return TokenResult(
        token=create_access_token(user.id),
        refresh_token=refresh,
        user=UserOut.model_validate(user),
    )


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=TokenResult)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResult:
    exists = await db.execute(select(User.id).where(User.username == body.username))
    if exists.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该手机号已注册")
    user = User(id=_new_user_id(), username=body.username, password_hash=hash_password(body.password))
    db.add(user)
    await db.flush()
    result = await _issue_tokens(db, user)
    await db.commit()
    return result


@router.post("/login", response_model=TokenResult)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResult:
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")
    return await _issue_tokens(db, user)


@router.post("/refresh", response_model=TokenResult)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResult:
    result = await db.execute(select(RefreshToken).where(RefreshToken.token == body.refresh_token))
    rt = result.scalar_one_or_none()
    if rt is None or rt.revoked:
        await db.rollback()
        raise _INVALID_TOKEN
    if rt.expires_at < utc_now():
        await db.rollback()
        raise _INVALID_TOKEN
    user = await db.get(User, rt.user_id)
    if user is None:
        await db.rollback()
        raise _INVALID_TOKEN
    # 轮换：旧刷新令牌置为撤销，签发一组新令牌
    rt.revoked = True
    result = await _issue_tokens(db, user)
    await db.commit()
    return result


@router.post("/logout", response_model=None)
async def logout(body: LogoutRequest | None = None, db: AsyncSession = Depends(get_db),
                 current: User = Depends(get_current_user)) -> dict[str, str]:
    query = select(RefreshToken).where(RefreshToken.user_id == current.id)
    if body and body.refresh_token:
        query = query.where(RefreshToken.token == body.refresh_token)
    else:
        query = query.where(RefreshToken.revoked.is_(False))
    for rt in (await db.execute(query)).scalars():
        rt.revoked = True
    await db.commit()
    return {"detail": "ok"}


@router.get("/me", response_model=UserOut)
async def me(current: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current)
