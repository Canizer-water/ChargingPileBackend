from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class UserSetting(Base):
    """自动断电偏好（设计文档 §4 user_settings）。一行一用户，懒创建。"""

    __tablename__ = "user_settings"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    auto_stop: Mapped[bool] = mapped_column(Boolean, default=False)
    stop_energy_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    stop_threshold: Mapped[float] = mapped_column(Float, default=90.0)
