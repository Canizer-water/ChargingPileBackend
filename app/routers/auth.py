"""认证端点：register / login / me（设计文档 §5.1）。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.user import LoginRequest, RegisterRequest, TokenResult, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def _new_user_id() -> str:
    return f"U{uuid.uuid4().hex[:12]}"


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=TokenResult)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResult:
    exists = await db.execute(select(User.id).where(User.username == body.username))
    if exists.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该手机号已注册")
    user = User(id=_new_user_id(), username=body.username, password_hash=hash_password(body.password))
    db.add(user)
    await db.commit()
    return TokenResult(token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenResult)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResult:
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")
    return TokenResult(token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(current: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current)
