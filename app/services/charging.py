"""充电会话业务规则与设计文档 §4 不变式（start/stop/current 的唯一裁决处）。

不变式：
1. 一个用户至多 1 个 CHARGING 订单；
2. 订单进行期间桩 status=CHARGING，结算后回 IDLE；
3. FINISHED 订单不可变。
（SQLite 单写者场景以应用层校验保证；切 MySQL 并发写时此处需加事务级锁，见三期 TODO。）
"""

from __future__ import annotations

import random
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import utc_now
from app.models.order import ChargingOrder, OrderStatus
from app.models.pile import Pile, PileStatus
from app.models.station import Station
from app.schemas.charging import EstimateOut, RealtimeOut
from app.services.realtime import get_provider


class BizError(Exception):
    """业务失败：由 main 的异常处理器转成 {"detail": msg} 响应。"""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _gen_order_id(now: datetime) -> str:
    return f"CO{now:%Y%m%d%H%M%S}{random.randint(1000, 9999)}"


async def _pile_by_code(db: AsyncSession, code: str) -> Pile | None:
    result = await db.execute(select(Pile).where(Pile.code == code))
    return result.scalar_one_or_none()


async def get_active_order(db: AsyncSession, user_id: str) -> ChargingOrder | None:
    result = await db.execute(
        select(ChargingOrder)
        .where(ChargingOrder.user_id == user_id, ChargingOrder.status == OrderStatus.CHARGING.value)
        .order_by(ChargingOrder.start_time.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def start_order(db: AsyncSession, user_id: str, pile_id: str) -> ChargingOrder:
    pile = await db.get(Pile, pile_id)
    if pile is None:
        raise BizError(404, "充电桩不存在")
    if pile.status != PileStatus.IDLE.value:
        raise BizError(409, "该充电桩当前不可用")
    if await get_active_order(db, user_id) is not None:
        raise BizError(409, "已有进行中的充电订单，请先结束")

    station = await db.get(Station, pile.station_id)
    now = utc_now()
    order = ChargingOrder(
        id=_gen_order_id(now),
        user_id=user_id,
        station_id=pile.station_id,
        station_name=station.name if station else "",
        pile_code=pile.code,
        start_time=now,
        end_time=None,
        energy_kwh=0.0,
        unit_price=pile.price_per_kwh,
        duration_min=0,
        amount=0.0,
        status=OrderStatus.CHARGING.value,
    )
    pile.status = PileStatus.CHARGING.value
    db.add(order)
    await db.commit()
    return order


async def stop_order(db: AsyncSession, user_id: str, order_id: str) -> ChargingOrder:
    order = await db.get(ChargingOrder, order_id)
    # 越权与不存在同回 404，不泄露资源存在性（§6）
    if order is None or order.user_id != user_id:
        raise BizError(404, "订单不存在")
    if order.status == OrderStatus.FINISHED.value:
        raise BizError(409, "订单已结束")

    pile = await _pile_by_code(db, order.pile_code)
    if pile is None:
        raise BizError(409, "桩档案缺失，无法结算")

    now = utc_now()
    snap = get_provider().snapshot(order, pile, now)
    order.end_time = now
    order.duration_min = max(1, round(snap.duration_sec / 60))
    order.energy_kwh = snap.energy_kwh
    order.amount = round(snap.energy_kwh * order.unit_price, 2)
    order.status = OrderStatus.FINISHED.value
    pile.status = PileStatus.IDLE.value
    await db.commit()
    return order


async def current_realtime(db: AsyncSession, user_id: str) -> tuple[ChargingOrder, RealtimeOut]:
    order = await get_active_order(db, user_id)
    if order is None:
        raise BizError(404, "没有进行中的充电会话")
    pile = await _pile_by_code(db, order.pile_code)
    if pile is None:
        raise BizError(409, "桩档案缺失，无法提供实时数据")
    return order, get_provider().snapshot(order, pile, utc_now())


async def estimate_order(db: AsyncSession, pile_id: str, expected_minutes: int) -> EstimateOut:
    """费用预估（C 域 · Story 10）：预计电量 = 功率 × 时长，费用 = 电量 × 单价。

    仅供参考，最终以 stop 结算为准；桩不存在/不可用（含 FAULT）一律拒绝。
    """
    pile = await db.get(Pile, pile_id)
    if pile is None:
        raise BizError(404, "充电桩不存在")
    if pile.status != PileStatus.IDLE.value:
        raise BizError(409, "该充电桩当前不可用")

    expected_energy_kwh = round(pile.power_kw * expected_minutes / 60, 2)
    estimated_cost = round(expected_energy_kwh * pile.price_per_kwh, 2)
    return EstimateOut(
        pile_id=pile.id,
        unit_price=pile.price_per_kwh,
        power_kw=pile.power_kw,
        expected_energy_kwh=expected_energy_kwh,
        estimated_cost=estimated_cost,
    )
