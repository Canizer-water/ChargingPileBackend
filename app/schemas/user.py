from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.common import CamelModel


class RegisterRequest(CamelModel):
    # 校验口径与前端注册页一致：11 位手机号 + 6-20 位密码
    username: str = Field(pattern=r"^\d{11}$")
    password: str = Field(min_length=6, max_length=20)


class LoginRequest(CamelModel):
    username: str
    password: str


class UserOut(CamelModel):
    id: str
    username: str
    avatar: str
    created_at: datetime


class TokenResult(CamelModel):
    token: str
    refresh_token: str
    user: UserOut


class RefreshRequest(CamelModel):
    refresh_token: str


class LogoutRequest(CamelModel):
    refresh_token: str | None = None


class ProfileUpdateRequest(CamelModel):
    avatar: str | None = None
