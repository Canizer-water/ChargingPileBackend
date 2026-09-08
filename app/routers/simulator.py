"""B2 独立模拟充电桩 REST 上报端点（scripts/charger_sim.py 使用）。

设备协议：register →（heartbeat + telemetry × N）→ done；
注册表与遥测均在进程内，后端重启后模拟器重新注册即可。
桩状态一律以 piles 表为准；除结算释放外本模块不改 pile.status（见 services/charging.py）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_db
from app.core.timeutil import utc_now
from app.models.order import ChargingOrder, OrderStatus
from app.models.pile import Pile
from app.schemas.charging import RealtimeOut
from app.schemas.simulator import (
    SimulatorDoneResponse,
    SimulatorRegisterRequest,
    SimulatorRegisterResponse,
    SimulatorStateResponse,
    SimulatorTelemetryRequest,
)
from app.services.charging import BizError, settle_active_order_for_pile
from app.services.simulator import registry, update_telemetry

router = APIRouter(prefix="/simulator", tags=["simulator"])


async def _pile_by_code(db: AsyncSession, pile_code: str) -> Pile | None:
    result = await db.execute(select(Pile).where(Pile.code == pile_code))
    return result.scalar_one_or_none()


@router.post("/register", response_model=SimulatorRegisterResponse)
async def register_device(body: SimulatorRegisterRequest,
                          db: AsyncSession = Depends(get_db)) -> SimulatorRegisterResponse:
    pile = await _pile_by_code(db, body.pile_code)
    if pile is None:
        raise BizError(404, "充电桩不存在")

    pile_owner = registry.pile_owner(body.pile_code)
    if pile_owner is not None and pile_owner.device_id != body.device_id:
        raise BizError(409, "该桩已被其他模拟设备注册")

    device = registry.register(body.device_id, body.pile_code)
    return SimulatorRegisterResponse(
        simulator_id=device.simulator_id,
        device_id=device.device_id,
        pile_code=device.pile_code,
        pile_status=pile.status,
        heartbeat_interval_sec=get_settings().simulator_heartbeat_interval_sec,
    )


@router.post("/{simulator_id}/heartbeat", response_model=SimulatorStateResponse)
async def heartbeat(simulator_id: str, db: AsyncSession = Depends(get_db)) -> SimulatorStateResponse:
    device = registry.touch(simulator_id)
    if device is None:
        raise BizError(404, "模拟设备不存在或已下线，请重新注册")
    pile = await _pile_by_code(db, device.pile_code)
    return SimulatorStateResponse(
        simulator_id=device.simulator_id,
        pile_code=device.pile_code,
        pile_status=pile.status if pile else "OFFLINE",
        online=device.online,
    )


@router.post("/{simulator_id}/telemetry", response_model=SimulatorStateResponse)
async def telemetry(simulator_id: str, body: SimulatorTelemetryRequest,
                    db: AsyncSession = Depends(get_db)) -> SimulatorStateResponse:
    device = registry.get(simulator_id)
    if device is None:
        raise BizError(404, "模拟设备不存在或已下线，请重新注册")
    pile = await _pile_by_code(db, device.pile_code)
    if pile is None:
        raise BizError(404, "充电桩不存在")

    # 会话时长/费用由后端依据库内进行中订单补齐，遥测只送桩侧计量值（裁决权在后端）。
    order = (
        await db.execute(
            select(ChargingOrder)
            .where(ChargingOrder.pile_code == device.pile_code,
                   ChargingOrder.status == OrderStatus.CHARGING.value)
            .order_by(ChargingOrder.start_time.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    duration_sec = 0.0
    unit_price = pile.price_per_kwh
    if order is not None:
        duration_sec = max(0.0, (utc_now() - order.start_time).total_seconds())
        unit_price = order.unit_price

    update_telemetry(
        device.pile_code,
        RealtimeOut(
            voltage=round(body.voltage, 1),
            current=round(body.current, 1),
            power_kw=round(body.power_kw, 1),
            duration_sec=round(duration_sec, 0),
            energy_kwh=round(body.energy_kwh, 2),
            estimated_cost=round(body.energy_kwh * unit_price, 2),
        ),
    )
    return SimulatorStateResponse(
        simulator_id=device.simulator_id,
        pile_code=device.pile_code,
        pile_status=pile.status,
        online=device.online,
    )


@router.post("/{simulator_id}/done", response_model=SimulatorDoneResponse)
async def done(simulator_id: str, db: AsyncSession = Depends(get_db)) -> SimulatorDoneResponse:
    device = registry.get(simulator_id)
    if device is None:
        raise BizError(404, "模拟设备不存在或已下线，请重新注册")
    settled = await settle_active_order_for_pile(db, device.pile_code)
    settled_id = settled.id if settled is not None else ""
    return SimulatorDoneResponse(
        simulator_id=device.simulator_id,
        pile_code=device.pile_code,
        pile_status="IDLE",
        online=device.online,
        settled_order_id=settled_id,
    )
