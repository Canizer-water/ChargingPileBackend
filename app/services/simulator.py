"""B2 模拟桩设备注册表（进程内，重启可重新注册）。

只维护「设备 ↔ 桩」映射与最近心跳/遥测，不写 pile.status、不碰订单；
桩状态与结算裁决始终在 services/charging.py（防割裂红线：模拟器只上报数据）。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from app.mqtt.consumer import SNAPSHOT_CACHE
from app.schemas.charging import RealtimeOut


#: 心跳超时（秒）：超过视为设备离线（仅影响本注册表 online 状态，不改库内桩状态）
HEARTBEAT_TIMEOUT_SEC = 30.0


@dataclass
class SimulatorDevice:
    simulator_id: str
    device_id: str
    pile_code: str
    created_at: float = field(default_factory=time.monotonic)
    last_heartbeat_at: float = field(default_factory=time.monotonic)

    @property
    def online(self) -> bool:
        return time.monotonic() - self.last_heartbeat_at <= HEARTBEAT_TIMEOUT_SEC


class SimulatorRegistry:
    """设备注册表：simulator_id 与 pile_code 双向索引（单进程内唯一）。"""

    def __init__(self) -> None:
        self._by_id: dict[str, SimulatorDevice] = {}
        self._by_pile: dict[str, str] = {}

    def register(self, device_id: str, pile_code: str) -> SimulatorDevice:
        existing = self.find_by_device(device_id)
        if existing is not None:
            if existing.pile_code == pile_code:
                device = self.touch(existing.simulator_id)
                return device if device is not None else existing
            self.reregister(existing.simulator_id, device_id, pile_code)
            return self._by_id[existing.simulator_id]
        sim_id = f"SIM-{uuid.uuid4().hex[:12]}"
        device = SimulatorDevice(simulator_id=sim_id, device_id=device_id, pile_code=pile_code)
        self._by_id[sim_id] = device
        self._by_pile[pile_code] = sim_id
        return device

    def find_by_device(self, device_id: str) -> SimulatorDevice | None:
        for device in self._by_id.values():
            if device.device_id == device_id:
                return device
        return None

    def reregister(self, simulator_id: str, device_id: str, pile_code: str) -> SimulatorDevice:
        """模拟器重启复用 simulator_id 重新注册：整体替换旧映射，防止孤儿绑定。"""
        old = self._by_id.pop(simulator_id, None)
        if old is not None and self._by_pile.get(old.pile_code) == simulator_id:
            self._by_pile.pop(old.pile_code, None)
            if old.pile_code != pile_code:
                SNAPSHOT_CACHE.remove(old.pile_code)
        device = SimulatorDevice(simulator_id=simulator_id, device_id=device_id, pile_code=pile_code)
        self._by_id[simulator_id] = device
        self._by_pile[pile_code] = simulator_id
        return device

    def get(self, simulator_id: str) -> SimulatorDevice | None:
        return self._by_id.get(simulator_id)

    def pile_owner(self, pile_code: str) -> SimulatorDevice | None:
        sim_id = self._by_pile.get(pile_code)
        return self._by_id.get(sim_id) if sim_id else None

    def touch(self, simulator_id: str) -> SimulatorDevice | None:
        device = self._by_id.get(simulator_id)
        if device is not None:
            device.last_heartbeat_at = time.monotonic()
        return device

    def unregister(self, simulator_id: str) -> SimulatorDevice | None:
        device = self._by_id.pop(simulator_id, None)
        if device is not None and self._by_pile.get(device.pile_code) == simulator_id:
            self._by_pile.pop(device.pile_code, None)
            SNAPSHOT_CACHE.remove(device.pile_code)  # 清理该桩的遥测缓存
        return device

    def clear(self) -> None:
        self._by_id.clear()
        self._by_pile.clear()
        SNAPSHOT_CACHE.clear()


#: 进程级单例（app 与 tests 共享）
registry = SimulatorRegistry()


def update_telemetry(pile_code: str, data: RealtimeOut) -> None:
    """写入最新遥测帧（与 MQTT 消费侧共用同一快照缓存，保证实时链路单一来源）。"""
    SNAPSHOT_CACHE.update(pile_code, data)


def clear_telemetry(pile_code: str) -> None:
    """会话结束清理该桩遥测，避免陈旧帧被误当作实时数据。"""
    SNAPSHOT_CACHE.remove(pile_code)
