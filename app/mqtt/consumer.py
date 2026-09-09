"""MQTT 接入桩（三期，已激活）：paho 线程订阅桩实时上报 → SnapshotCache。

Windows 默认 Proactor 事件循环不支持 asyncio 的 add_reader，aiomqtt 会因此报错；
改用 paho-mqtt 自带网络线程（loop_start），对 FastAPI 的异步主循环无侵入。
"""

from __future__ import annotations

import json
import logging
import ssl
import time
from dataclasses import dataclass

import paho.mqtt.client as mqtt

from app.core.config import get_settings
from app.mqtt.topics import TOPIC_PREFIX
from app.schemas.charging import RealtimeOut

logger = logging.getLogger(__name__)

#: 桩实时上报订阅通配：{prefix}/{pile_code}/charging/up（占位前缀，接入后按产品 topic 校准）
TOPIC_PILE_UP_PATTERN = f"{TOPIC_PREFIX}/+/charging/up"


@dataclass
class RealtimeSnapshot:
    """单桩最近一次上报的实时数据。"""

    received_at: float  # time.monotonic()
    data: RealtimeOut


class SnapshotCache:
    """内存缓存 {pile_code: RealtimeSnapshot}。

    MQTT consumer 任务写入；读取方可据 age 判断数据新鲜度，
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

    def remove(self, pile_code: str) -> None:
        self._snapshots.pop(pile_code, None)

    def clear(self) -> None:
        self._snapshots.clear()


#: 进程级单例（与 realtime provider 共享）
SNAPSHOT_CACHE = SnapshotCache()

_client: mqtt.Client | None = None


def _num(data: dict, *keys: str) -> float:
    for k in keys:
        v = data.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0


def _pile_code_from_topic(topic: str) -> str | None:
    """自占位主题 `t/{pile}/charging/up` 提取桩码；非本前缀返回 None。"""
    parts = topic.strip("/").split("/")
    if len(parts) >= 3 and parts[0] == "t":
        return parts[2]
    return None


def _realtime_from_payload(payload: bytes) -> tuple[str | None, RealtimeOut]:
    """把上报载荷解析成 RealtimeOut；桩码优先取载荷里的 pileCode/pile_code。

    载荷为任意数值键（camel 或 snake 皆可），缺失项按 0；费用未给时按电量×单价估算。
    """
    try:
        data = json.loads(payload.decode("utf-8", "replace"))
    except (ValueError, UnicodeDecodeError):
        logger.warning("MQTT payload 非 JSON，忽略: %.120r", payload[:120])
        return None, RealtimeOut(voltage=0, current=0, power_kw=0, duration_sec=0,
                                 energy_kwh=0, estimated_cost=0)
    if not isinstance(data, dict):
        return None, RealtimeOut(voltage=0, current=0, power_kw=0, duration_sec=0,
                                 energy_kwh=0, estimated_cost=0)

    pile_code = data.get("pileCode") or data.get("pile_code")
    pile_code = str(pile_code) if pile_code else None
    energy_kwh = _num(data, "energyKwh", "energy_kwh")
    unit_price = _num(data, "unitPrice", "unit_price")
    estimated = _num(data, "estimatedCost", "estimated_cost")
    return pile_code, RealtimeOut(
        voltage=_num(data, "voltage"),
        current=_num(data, "current"),
        power_kw=_num(data, "powerKw", "power_kw"),
        duration_sec=_num(data, "durationSec", "duration_sec"),
        energy_kwh=energy_kwh,
        estimated_cost=estimated if estimated > 0 else round(energy_kwh * unit_price, 2),
    )


def _on_connect(client: mqtt.Client, userdata, flags, reason_code, properties=None) -> None:
    code = reason_code.value if hasattr(reason_code, "value") else reason_code
    if code != 0:
        logger.error("MQTT connect refused, code=%s", code)
        return
    logger.info("MQTT CONNACK OK，订阅 %s", TOPIC_PILE_UP_PATTERN)
    client.subscribe(TOPIC_PILE_UP_PATTERN, qos=0)


def _on_message(client: mqtt.Client, userdata, msg: mqtt.MQTTMessage) -> None:
    topic = str(msg.topic)
    pile_code, snap = _realtime_from_payload(msg.payload)
    if pile_code is None:
        pile_code = _pile_code_from_topic(topic)
    if pile_code is None:
        logger.warning("MQTT topic 无桩码且载荷无 pileCode，忽略: %s", topic)
        return
    SNAPSHOT_CACHE.update(pile_code, snap)
    logger.debug("MQTT pile %s 遥测已缓存 (energy=%.2f)", pile_code, snap.energy_kwh)


def start_consumer() -> None:
    """激活 MQTT：paho 线程连接华为云 IoTDA（MQTTS），订阅并写 SnapshotCache。

    由 app.main 的 lifespan 在 Settings.mqtt_enabled 时调用；连接失败抛异常由调用方处理。
    """
    global _client
    settings = get_settings()
    if not settings.mqtt_enabled:
        raise RuntimeError("MQTT_ENABLED=false，未激活")
    if _client is not None:
        return
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id=settings.mqtt_client_id or None)
    client.username_pw_set(settings.mqtt_username, settings.mqtt_access_token or None)
    client.tls_set_context(ssl.create_default_context())
    client.on_connect = _on_connect
    client.on_message = _on_message
    client.connect(settings.mqtt_host, settings.mqtt_port, keepalive=30)
    client.loop_start()
    _client = client
    logger.info("MQTT consumer 已启动: %s:%s", settings.mqtt_host, settings.mqtt_port)


def stop_consumer() -> None:
    """停掉 MQTT 线程并断开（app 关闭时调用）。"""
    global _client
    if _client is not None:
        _client.loop_stop()
        try:
            _client.disconnect()
        except Exception:  # noqa: BLE001 - 关闭阶段忽略网络异常
            pass
        _client = None
