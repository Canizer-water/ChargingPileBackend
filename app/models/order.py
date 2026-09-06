from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class OrderStatus(str, enum.Enum):
    CHARGING = "CHARGING"
    FINISHED = "FINISHED"


class ChargingOrder(Base):
    """充电订单 = 会话。station_name/pile_code 冗余存储历史凭证（§4）。"""

    __tablename__ = "charging_orders"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    station_id: Mapped[str] = mapped_column(String(16), ForeignKey("stations.id"))
    station_name: Mapped[str] = mapped_column(String(64), default="")
    pile_code: Mapped[str] = mapped_column(String(16))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=lambda: datetime.now(timezone.utc))
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    energy_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    unit_price: Mapped[float] = mapped_column(Float)  # 下单时快照桩单价
    duration_min: Mapped[int] = mapped_column(Integer, default=0)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default=OrderStatus.CHARGING.value)

    user: Mapped["User"] = relationship()  # noqa: F821
