from __future__ import annotations

from typing import Literal

from app.schemas.common import CamelModel, fmt_datetime

OrderStatusLiteral = Literal["CHARGING", "FINISHED"]


class OrderOut(CamelModel):
    """字段与前端 ChargingOrder 逐一对齐；endTime 进行中返回 ''（§5.4）。"""

    id: str
    station_id: str
    station_name: str
    pile_code: str
    start_time: str
    end_time: str
    energy_kwh: float
    unit_price: float
    duration_min: int
    amount: float
    status: OrderStatusLiteral


def order_to_out(order) -> OrderOut:
    return OrderOut(
        id=order.id,
        station_id=order.station_id,
        station_name=order.station_name,
        pile_code=order.pile_code,
        start_time=fmt_datetime(order.start_time),
        end_time=fmt_datetime(order.end_time),
        energy_kwh=order.energy_kwh,
        unit_price=order.unit_price,
        duration_min=order.duration_min,
        amount=order.amount,
        status=order.status,  # type: ignore[arg-type]
    )
