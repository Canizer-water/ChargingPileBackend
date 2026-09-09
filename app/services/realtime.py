"""实时数据提供者（设计文档 §7 三期共用抽象）。

RealtimeProvider.snapshot(order, pile, now) 是唯一取数入口；
sim=无状态推导（可测试、重启不丢会话），simulator=独立模拟桩 REST 遥测（B2），
mqtt=读桩上报缓存（三期）；后两者陈旧/缺数据时自动回退 sim。
"""

from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import Protocol

from app.core.config import get_settings
from app.models.order import ChargingOrder
from app.models.pile import Pile
from app.mqtt.consumer import SNAPSHOT_CACHE, RealtimeSnapshot
from app.schemas.charging import RealtimeOut

logger = logging.getLogger(__name__)

#: 数据新鲜度阈值（秒）：MQTT 缓存超过该时长视为陈旧，回退模拟
SNAPSHOT_STALE_SECONDS = 10.0


def _energy_at(pile_power_kw: float, t_sec: float) -> float:
    """dE/dt = P0·max(0.5, 0.8 − E/400)/3600 的解析解（E 单位 kWh，t 单位秒）。

    E < 120 段：E(t) = 320·(1 − e^(−b·t))，b = P0/1,440,000；
    此后功率锁定 0.5 倍额定，线性累加。
    """
    if pile_power_kw <= 0:
        return 0.0
    t_sec = max(t_sec, 0.0)
    b = pile_power_kw / 1_440_000.0
    t_switch = math.log(1.6) / b  # E(t_switch) = 120
    if t_sec <= t_switch:
        return 320.0 * (1.0 - math.exp(-b * t_sec))
    return 120.0 + 0.5 * pile_power_kw * (t_sec - t_switch) / 3600.0


def simulate_snapshot(unit_price: float, pile_power_kw: float, started_at: datetime, now: datetime) -> RealtimeOut:
    """从会话起始时间无状态推导当前 tick（确定性：伪抖动用 sin(t)，无随机数）。"""
    t_sec = max((now - started_at).total_seconds(), 0.0)
    energy = _energy_at(pile_power_kw, t_sec)
    energy_kwh = round(energy, 2)
    factor = max(0.5, 0.8 - energy / 400.0)
    power = pile_power_kw * factor
    voltage = 720.0 + 30.0 * math.sin(t_sec / 7.0)
    current = power * 1000.0 / voltage
    return RealtimeOut(
        voltage=round(voltage, 1),
        current=round(current, 1),
        power_kw=round(power, 1),
        duration_sec=round(t_sec, 0),
        energy_kwh=energy_kwh,
        estimated_cost=round(energy_kwh * unit_price, 2),
    )


class RealtimeProvider(Protocol):
    def snapshot(self, order: ChargingOrder, pile: Pile, now: datetime) -> RealtimeOut: ...


class SimulatedProvider:
    """一期：纯服务端模拟。"""

    def snapshot(self, order: ChargingOrder, pile: Pile, now: datetime) -> RealtimeOut:
        return simulate_snapshot(order.unit_price, pile.power_kw, order.start_time, now)


class SimulatorTelemetryProvider:
    """二期 B2：独立模拟桩经 REST 上报的遥测优先；无数据/陈旧时回退 SimulatedProvider。

    与 MqttProvider 同构：桩码不在缓存或数据陈旧时回退模拟，保证 GET/WS 永不空窗。
    """

    def __init__(self) -> None:
        self._fallback = SimulatedProvider()

    def snapshot(self, order: ChargingOrder, pile: Pile, now: datetime) -> RealtimeOut:
        snap: RealtimeSnapshot | None = SNAPSHOT_CACHE.get(order.pile_code)
        if snap is None:
            return self._fallback.snapshot(order, pile, now)
        age = SNAPSHOT_CACHE.age_seconds(order.pile_code)
        if age is not None and age > SNAPSHOT_STALE_SECONDS:
            logger.warning("pile %s simulator telemetry stale (%.1fs), fallback to simulation",
                           order.pile_code, age)
            return self._fallback.snapshot(order, pile, now)
        return snap.data


class MqttProvider:
    """三期：读 MQTT 上报缓存；桩码不在缓存或数据陈旧时回退模拟并告警。"""

    def __init__(self) -> None:
        self._fallback = SimulatedProvider()

    def snapshot(self, order: ChargingOrder, pile: Pile, now: datetime) -> RealtimeOut:
        snap: RealtimeSnapshot | None = SNAPSHOT_CACHE.get(order.pile_code)
        if snap is None:
            logger.warning("pile %s has no mqtt snapshot, fallback to simulation", order.pile_code)
            return self._fallback.snapshot(order, pile, now)
        age = SNAPSHOT_CACHE.age_seconds(order.pile_code)
        if age is not None and age > SNAPSHOT_STALE_SECONDS:
            logger.warning("pile %s snapshot stale (%.1fs), fallback to simulation", order.pile_code, age)
            return self._fallback.snapshot(order, pile, now)
        return snap.data


_provider: RealtimeProvider | None = None


def get_provider() -> RealtimeProvider:
    global _provider
    if _provider is None:
        source = get_settings().realtime_source
        if source == "mqtt":
            _provider = MqttProvider()
        elif source == "simulator":
            _provider = SimulatorTelemetryProvider()
        else:
            _provider = SimulatedProvider()
    return _provider
