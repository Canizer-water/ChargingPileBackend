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
from app.models.daily_stat import DailyChargingStat
from app.models.order import ChargingOrder, OrderStatus
from app.models.pile import Pile, PileStatus
from app.models.station import Station
from app.models.user_setting import UserSetting
from app.schemas.charging import EstimateOut, RealtimeOut
from app.services.realtime import get_provider
from app.services.simulator import clear_telemetry


class BizError(Exception):
    """业务失败：由 main 的异常处理器转成 {"detail": msg} 响应。"""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _gen_order_id(now: datetime) -> str:
    return f"CO{now:%Y%m%d%H%M%S}{random.randint(1000, 9999)}"


def _gen_stat_id(now: datetime) -> str:
    return f"DS{now:%Y%m%d%H%M%S}{random.randint(1000, 9999)}"


async def find_pile_by_code(db: AsyncSession, code: str) -> Pile | None:
    """按桩码（二维码内容）查桩，扫码解析入口共用。"""
    result = await db.execute(select(Pile).where(Pile.code == code))
    return result.scalar_one_or_none()


# 兼容内部旧引用
_pile_by_code = find_pile_by_code


async def get_active_order(db: AsyncSession, user_id: str) -> ChargingOrder | None:
    result = await db.execute(
        select(ChargingOrder)
        .where(ChargingOrder.user_id == user_id, ChargingOrder.status == OrderStatus.CHARGING.value)
        .order_by(ChargingOrder.start_time.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def require_active_session(
    db: AsyncSession, user_id: str, order_id: str
) -> tuple[ChargingOrder, Pile]:
    """会话订阅校验：必须是本人进行中的订单（越权/不存在/已结束 → 404，不泄露存在性）。"""
    order = await db.get(ChargingOrder, order_id)
    if order is None or order.user_id != user_id or order.status != OrderStatus.CHARGING.value:
        raise BizError(404, "没有进行中的充电会话")
    pile = await _pile_by_code(db, order.pile_code)
    if pile is None:
        raise BizError(409, "桩档案缺失，无法提供实时数据")
    return order, pile


async def _settle_order(db: AsyncSession, order: ChargingOrder) -> ChargingOrder:
    """结算并落 FINISHED（不变式 2/3）：桩档案缺失抛 409；完成后释放桩并清遥测。"""
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
    clear_telemetry(order.pile_code)
    await _upsert_daily_stat(db, order.user_id, order, now)
    await db.commit()
    return order


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
    return await _settle_order(db, order)


async def settle_active_order_for_pile(db: AsyncSession, pile_code: str) -> ChargingOrder | None:
    """设备完成上报（B2 /done）触发的裁决：桩上有进行中订单则按同一结算路径收官。

    桩空闲/无订单返回 None（设备报告“停充”时后端无可结算会话即视为幂等完成）；
    桩档案缺失抛 409。裁决权仍在本模块，模拟器只送数据、不落订单。
    """
    pile = await _pile_by_code(db, pile_code)
    if pile is None:
        raise BizError(404, "充电桩不存在")
    if pile.status != PileStatus.CHARGING.value:
        return None

    result = await db.execute(
        select(ChargingOrder)
        .where(ChargingOrder.pile_code == pile_code,
               ChargingOrder.status == OrderStatus.CHARGING.value)
        .order_by(ChargingOrder.start_time.desc())
        .limit(1)
    )
    order = result.scalar_one_or_none()
    if order is None:
        return None
    return await _settle_order(db, order)


async def get_or_create_settings(db: AsyncSession, user_id: str) -> UserSetting:
    """自动断电偏好：一行一用户，懒创建（无记录返回默认值，不落库）。"""
    row = await db.get(UserSetting, user_id)
    if row is None:
        row = UserSetting(user_id=user_id, auto_stop=False, stop_energy_kwh=0.0, stop_threshold=90.0)
    return row


async def set_settings(db: AsyncSession, user_id: str,
                       auto_stop: bool | None,
                       stop_energy_kwh: float | None,
                       stop_threshold: float | None) -> UserSetting:
    row = await db.get(UserSetting, user_id)
    if row is None:
        row = UserSetting(user_id=user_id, auto_stop=False, stop_energy_kwh=0.0, stop_threshold=90.0)
        db.add(row)
    if auto_stop is not None:
        row.auto_stop = auto_stop
    if stop_energy_kwh is not None:
        row.stop_energy_kwh = stop_energy_kwh
    if stop_threshold is not None:
        row.stop_threshold = stop_threshold
    await db.commit()
    return row


async def current_realtime(db: AsyncSession, user_id: str) -> tuple[ChargingOrder, RealtimeOut]:
    order = await get_active_order(db, user_id)
    if order is None:
        raise BizError(404, "没有进行中的充电会话")
    order, pile = await require_active_session(db, user_id, order.id)
    snap = get_provider().snapshot(order, pile, utc_now())
    stopped = await _auto_stop_if_needed(db, user_id, order, snap)
    if stopped:
        raise BizError(404, "没有进行中的充电会话")
    return order, snap


async def _upsert_daily_stat(db: AsyncSession, user_id: str, order: ChargingOrder, now: datetime) -> None:
    """结算后按 user_id+date（naive UTC 日期）upsert 当天累计（§4 daily_charging_stats）。"""
    date = order.end_time.date().isoformat()
    result = await db.execute(
        select(DailyChargingStat).where(DailyChargingStat.user_id == user_id, DailyChargingStat.date == date)
    )
    stat = result.scalar_one_or_none()
    if stat is None:
        stat = DailyChargingStat(
            id=_gen_stat_id(now), user_id=user_id, date=date,
            total_energy_kwh=order.energy_kwh, total_amount=order.amount, order_count=1,
        )
        db.add(stat)
    else:
        stat.total_energy_kwh = round(stat.total_energy_kwh + order.energy_kwh, 2)
        stat.total_amount = round(stat.total_amount + order.amount, 2)
        stat.order_count += 1


async def _auto_stop_if_needed(db: AsyncSession, user_id: str, order: ChargingOrder, snap: RealtimeOut) -> bool:
    """自动断电：开启 autoStop 且电量达到阈值时结算（仍走 stop_order，守不变式）。"""
    settings = await get_or_create_settings(db, user_id)
    if not settings.auto_stop or settings.stop_energy_kwh <= 0:
        return False
    if snap.energy_kwh < settings.stop_energy_kwh:
        return False
    await stop_order(db, user_id, order.id)
    return True


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
