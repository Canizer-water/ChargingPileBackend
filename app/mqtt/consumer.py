"""MQTT 接入桩（三期实现）。本期仅提供缓存骨架，供 services/realtime.MqttProvider 读取。"""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.schemas.charging import RealtimeOut


@dataclass
class RealtimeSnapshot:
    """单桩最近一次上报的实时数据。"""

    received_at: float  # time.monotonic()
    data: RealtimeOut


class SnapshotCache:
    """内存缓存 {pile_code: RealtimeSnapshot}。

    三期由 MQTT consumer 任务写入；读取方可据 age 判断数据新鲜度，
    陈旧时由 MqttProvider 回退模拟（见 services/realtime.py）。
    """

    def __init__(self) -> None:
        self._snapshots: dict[str, RealtimeSnapshot] = {}

    def update(self, pile_code: str, data: RealtimeOut) -> None:
        self._snapshots[pile_code] = RealtimeSnapshot(received_at=time.monotonic(), data=data)

    def get(self, pile_code: str) -> RealtimeSnapshot | None:
        return self._snapshots.get(pile_code)

    def age_seconds(self, pile_code: str) -> float | None:
        snap = self._snapshots.get(pile_code)
        return (time.monotonic() - snap.received_at) if snap else None


#: 进程级单例（与 realtime provider 共享）
SNAPSHOT_CACHE = SnapshotCache()


async def start_consumer() -> None:
    """三期实现：aiomqtt 连接华为云 IoTDA，订阅 TOPIC_PILE_UP 写入 SNAPSHOT_CACHE。

    本期调用即报错，防止误开启。
    """
    raise NotImplementedError("MQTT consumer 为三期预留：接入华为云 IoTDA 时实现（先 pip 添加 aiomqtt）")
