"""IoTDA 设备模拟回环桥（三期）：后端本地模拟"桩设备"，经 MQTT 上报华为 IoTDA，
再从设备影子拉回写 SNAPSHOT_CACHE，让实时链路真实"绕平台一圈"。

- 上报端：按 DB 桩状态（IDLE/CHARGING/FAULT）每 iotda_report_sec 秒用设备三元组
  MQTT 发布 `$oc/devices/{id}/sys/properties/report`（数值型属性，service_id=iotda_service_id）。
- 收端：每 iotda_poll_sec 秒按应用侧 REST 查两台设备影子 → properties → RealtimeOut → SNAPSHOT_CACHE。

权威源不变式：桩状态与会话以 DB（services/charging.py 裁决）为准，影子值仅作展示数据。
"""

from __future__ import annotations

import json
import logging
import math
import ssl
import sqlite3
import threading
import time
from datetime import datetime, timezone

from paho.mqtt import client as mqtt

from app.core.config import get_settings
from app.mqtt.consumer import SNAPSHOT_CACHE
from app.services.iotda import properties_to_realtime, query_shadow_properties

logger = logging.getLogger(__name__)

#: 桩码 → 设备（device_id = MQTT username）
_PILE_DEVICES = ("p000000002", "p000000003")

_thread: threading.Thread | None = None
_stop = threading.Event()
_device_clients: dict[str, mqtt.Client] = {}


def build_properties(status: str, power_kw: float, started_at: float | None,
                     now: float | None = None) -> dict:
    """按桩状态组上报帧（纯函数，供单测）：0=空闲 1=充电中 2=故障。

    CHARGING 时电量线性累计（E = P·t），电压加确定性伪抖动，时长用会话起止差。
    """
    now = time.time() if now is None else now
    if status == "CHARGING" and started_at is not None:
        dur = max(0.0, now - started_at)
        factor = max(0.6, 1.0 - (dur / 3600.0) * 0.05)  # 长时间缓慢降载，避免纯直线
        power = power_kw * factor
        energy_kwh = round(power_kw * dur / 3600.0, 2)
        voltage = 720.0 + 30.0 * math.sin(dur / 7.0)
        current = power * 1000.0 / voltage
        return {
            "voltage": round(voltage, 1),
            "current": round(current, 1),
            "powerKw": round(power, 1),
            "energyKwh": energy_kwh,
            "durationSec": int(dur),
            "pileStatus": 1,
        }
    if status == "IDLE":
        return {"voltage": 0, "current": 0, "powerKw": 0, "energyKwh": 0.0,
                "durationSec": 0, "pileStatus": 0}
    # OFFLINE/FAULT 等不可用态统一按故障上报
    return {"voltage": 0, "current": 0, "powerKw": 0, "energyKwh": 0.0,
            "durationSec": 0, "pileStatus": 2}


def _db_path() -> str:
    url = get_settings().database_url
    prefix = "sqlite+aiosqlite:///"
    return url[len(prefix):] if url.startswith(prefix) else url


def _to_epoch(s: str | None) -> float | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def read_pile_state(pile_code: str) -> tuple[str, float, float | None, float]:
    """同步只读查询桩状态/功率/进行中订单起始/订单单价（桥线程内使用，不污染异步会话）。"""
    try:
        con = sqlite3.connect(f"file:{_db_path()}?mode=ro", uri=True, timeout=3)
    except sqlite3.Error:
        logger.warning("device_bridge: 无法打开 DB %s", _db_path())
        return "UNKNOWN", 0.0, None, 0.0
    try:
        row = con.execute(
            """
            SELECT p.status, p.power_kw,
                   (SELECT o.start_time FROM charging_orders o
                     WHERE o.pile_code = p.code AND o.status = 'CHARGING'
                     ORDER BY o.start_time DESC LIMIT 1),
                   (SELECT o.unit_price FROM charging_orders o
                     WHERE o.pile_code = p.code AND o.status = 'CHARGING'
                     ORDER BY o.start_time DESC LIMIT 1)
            FROM piles p WHERE p.code = ?
            """, (pile_code,)
        ).fetchone()
    finally:
        con.close()
    if row is None:
        return "UNKNOWN", 0.0, None, 0.0
    status = str(row[0]).upper()
    power = float(row[1] or 0.0)
    started = _to_epoch(row[2])
    unit_price = float(row[3] or 0.0)
    return status, power, started, unit_price


def _report_topic(device_id: str) -> str:
    return f"$oc/devices/{device_id}/sys/properties/report"


def _ensure_client(device_id: str) -> mqtt.Client | None:
    settings = get_settings()
    is1 = device_id == settings.iotda_device1_id
    username = settings.mqtt_username if is1 else settings.mqtt2_username
    password = settings.mqtt_access_token if is1 else settings.mqtt2_access_token
    client_id = settings.mqtt_client_id if is1 else settings.mqtt2_client_id
    cl = _device_clients.get(device_id)
    if cl is None:
        cl = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id or None)
        cl.username_pw_set(username, password or None)
        cl.tls_set_context(ssl.create_default_context())
        _device_clients[device_id] = cl
    if not cl.is_connected():
        try:
            cl.connect(settings.mqtt_host, settings.mqtt_port, keepalive=30)
            cl.loop_start()
            logger.info("device_bridge: 设备 %s MQTT 已连接", device_id)
        except Exception:  # noqa: BLE001 - 桥线程内重试，不中断主流程
            logger.warning("device_bridge: 设备 %s MQTT 连接失败（下轮重试）", device_id, exc_info=True)
            return None
    return cl


def _report_once(device_id: str, pile_code: str) -> None:
    cl = _ensure_client(device_id)
    if cl is None:
        return
    status, power, started, _unit_price = read_pile_state(pile_code)
    if status == "UNKNOWN":
        return
    props = build_properties(status, power, started)
    payload = {"services": [{"service_id": get_settings().iotda_service_id, "properties": props}]}
    try:
        cl.publish(_report_topic(device_id), json.dumps(payload), qos=1)
    except Exception:  # noqa: BLE001
        logger.warning("device_bridge: 发布失败 device=%s pile=%s", device_id, pile_code, exc_info=True)


def _poll_once(device_id: str, pile_code: str) -> None:
    props = query_shadow_properties(device_id)
    if props is None:
        return
    _, _, _, unit_price = read_pile_state(pile_code)
    SNAPSHOT_CACHE.update(pile_code, properties_to_realtime(props, unit_price))
    logger.debug("device_bridge: 影子 %s → cache[%s]", device_id, pile_code)


def _bridge_loop() -> None:
    settings = get_settings()
    dev1, dev2 = settings.iotda_device1_id, settings.iotda_device2_id
    last_report = last_poll = 0.0
    while not _stop.is_set():
        now = time.time()
        if now - last_report >= settings.iotda_report_sec:
            _report_once(dev1, _PILE_DEVICES[0])
            _report_once(dev2, _PILE_DEVICES[1])
            last_report = now
        if now - last_poll >= settings.iotda_poll_sec:
            _poll_once(dev1, _PILE_DEVICES[0])
            _poll_once(dev2, _PILE_DEVICES[1])
            last_poll = now
        _stop.wait(1.0)
    for cl in _device_clients.values():
        try:
            cl.loop_stop()
            cl.disconnect()
        except Exception:  # noqa: BLE001
            pass
    _device_clients.clear()


def start_bridge() -> None:
    """激活回环桥：由 main lifespan 在 Settings.iotda_enabled 时调用。"""
    global _thread
    settings = get_settings()
    if not settings.iotda_enabled:
        raise RuntimeError("IOTDA_ENABLED=false，未激活")
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_bridge_loop, name="iotda-device-bridge", daemon=True)
    _thread.start()
    logger.info("device_bridge 已启动（report=%ss poll=%ss）", settings.iotda_report_sec, settings.iotda_poll_sec)


def stop_bridge() -> None:
    """停桥并断开设备连接（app 关闭时调用）。"""
    global _thread
    _stop.set()
    if _thread is not None:
        _thread.join(timeout=5)
        _thread = None
