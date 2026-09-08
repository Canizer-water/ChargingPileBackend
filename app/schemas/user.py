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
    user: UserOut


class UserSettingsOut(CamelModel):
    """自动断电偏好（设计文档 §5.5）。与前端 Types.ets: UserSettings 对齐。"""

    auto_stop: bool
    stop_energy_kwh: float
    stop_threshold: float


class UserSettingsUpdate(CamelModel):
    auto_stop: bool | None = None
    stop_energy_kwh: float | None = None
    stop_threshold: float | None = None
