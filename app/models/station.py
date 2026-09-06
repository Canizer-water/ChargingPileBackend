from __future__ import annotations

from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Station(Base):
    """充电站。freePiles 不入库，由 piles 聚合派生（设计文档 §4）。"""

    __tablename__ = "stations"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    address: Mapped[str] = mapped_column(String(128))
    distance_km: Mapped[float] = mapped_column(Float, default=0.0)
    price_per_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    business_hours: Mapped[str] = mapped_column(String(32), default="00:00-24:00")

    piles: Mapped[list["Pile"]] = relationship(  # noqa: F821
        back_populates="station", lazy="selectin"
    )
