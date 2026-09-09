"""IoTDA 影子 / 设备模拟桥 —— 离线单测（不连云）。

覆盖：影子 service 解析、属性→RealtimeOut 映射（含字符串数字）、上报帧组帧语义。
"""

from __future__ import annotations

from app.services.device_bridge import build_properties
from app.services.iotda import extract_properties, properties_to_realtime


# ---------- 影子解析 ----------

def test_extract_properties_picks_target_service():
    shadow = [
        {"service_id": "other", "reported": {"properties": {"x": 1}}},
        {"service_id": "test", "reported": {"properties": {"voltage": 720.0, "pileStatus": 1}}},
        {"service_id": "test", "reported": {"properties": {"voltage": 999}}},  # 第二个同 service 只取第一个
    ]
    assert extract_properties(shadow, "test") == {"voltage": 720.0, "pileStatus": 1}


def test_extract_properties_empty_or_missing():
    assert extract_properties([], "test") is None
    assert extract_properties([{"service_id": "a", "reported": {}}], "test") is None


# ---------- 属性 → RealtimeOut ----------

def test_properties_to_realtime_numbers_and_string_numerals():
    rt = properties_to_realtime(
        {"voltage": "720.5", "current": 35, "powerKw": "150", "energyKwh": "0.6", "durationSec": "120"},
        unit_price=1.2,
    )
    assert rt.voltage == 720.5
    assert rt.current == 35.0
    assert rt.power_kw == 150.0
    assert rt.duration_sec == 120.0
    assert rt.energy_kwh == 0.6
    assert rt.estimated_cost == round(0.6 * 1.2, 2)


def test_properties_to_realtime_respects_given_cost():
    rt = properties_to_realtime({"energyKwh": 2.0, "estimatedCost": 3.5})
    assert rt.estimated_cost == 3.5


def test_properties_to_realtime_unknown_keys_zero():
    rt = properties_to_realtime({})
    assert (rt.voltage, rt.current, rt.power_kw, rt.duration_sec, rt.energy_kwh) == (0, 0, 0, 0, 0)


# ---------- 上报帧组帧 ----------

def test_build_idle():
    p = build_properties("IDLE", 150, None)
    assert p["pileStatus"] == 0
    assert p["powerKw"] == 0 and p["energyKwh"] == 0.0 and p["durationSec"] == 0
    assert isinstance(p["pileStatus"], int)


def test_build_charging_rises_over_time():
    base = build_properties("CHARGING", 150, started_at=0.0, now=3600)
    later = build_properties("CHARGING", 150, started_at=0.0, now=7200)
    assert base["pileStatus"] == 1 and later["pileStatus"] == 1
    assert base["durationSec"] == 3600 and later["durationSec"] == 7200
    assert later["energyKwh"] > base["energyKwh"]
    assert later["energyKwh"] > 0
    # 数值均为数字型
    for v in (base["voltage"], base["current"], base["powerKw"], base["energyKwh"]):
        assert isinstance(v, (int, float))


def test_build_unavailable_is_fault():
    for status in ("OFFLINE", "FAULT", "UNKNOWN"):
        p = build_properties(status, 150, None)
        assert p["pileStatus"] == 2
