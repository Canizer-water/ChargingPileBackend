from __future__ import annotations

import enum

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class PileStatus(str, enum.Enum):
    IDLE = "IDLE"
    CHARGING = "CHARGING"
    OFFLINE = "OFFLINE"


class Pile(Base):
    """充电桩。状态以库为准（修复前端内存翻转重启复位的技术债，§4）。"""

    __tablename__ = "piles"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    station_id: Mapped[str] = mapped_column(ForeignKey("stations.id"), index=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    power_kw: Mapped[float] = mapped_column(Float)
    price_per_kwh: Mapped[float] = mapped_column(Float)
    interface_type: Mapped[str] = mapped_column(String(32), default="")
    status: Mapped[str] = mapped_column(String(16), default=PileStatus.IDLE.value)

    station: Mapped["Station"] = relationship(back_populates="piles")  # noqa: F821
