"""车辆信息（C 域 · Story 4）：每用户至多一辆默认车辆。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutil import utc_now
from app.db import Base


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    plate_no: Mapped[str] = mapped_column(String(16), default="")
    battery: Mapped[int] = mapped_column(Integer, default=75)
    range_km: Mapped[int] = mapped_column(Integer, default=260)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
