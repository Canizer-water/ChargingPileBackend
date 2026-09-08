"""契约快照测试（设计文档 §9.2）：响应/请求模型字段集合与文档逐字对齐。

任何字段增删改必须先改文档再同步本测试，两端字段漂移即 CI 红。
"""

from __future__ import annotations

from app.schemas.charging import RealtimeOut, StartOrderRequest
from app.schemas.common import Envelope
from app.schemas.order import OrderOut, OrderPage
from app.schemas.scan import ScanResolveRequest
from app.schemas.station import PileOut, StationOut
from app.schemas.stat import DailyStatsOut
from app.schemas.user import (LoginRequest, RegisterRequest, TokenResult, UserOut,
                              UserSettingsOut, UserSettingsUpdate)

EXPECTED_KEYS: dict[str, set[str]] = {
    # 前端 Types.ets: UserAccount（去 password，服务端永不回传）
    "UserOut": {"id", "username", "avatar", "createdAt"},
    "TokenResult": {"token", "user"},
    "RegisterRequest": {"username", "password"},
    "LoginRequest": {"username", "password"},
    # 前端 Types.ets: ChargingPile
    "PileOut": {"id", "stationId", "code", "powerKw", "pricePerKwh", "interfaceType", "status"},
    # 前端 Types.ets: ChargingStation
    "StationOut": {"id", "name", "address", "distanceKm", "freePiles",
                   "pricePerKwh", "businessHours", "piles"},
    # 前端 Types.ets: ChargingOrder
    "OrderOut": {"id", "stationId", "stationName", "pileCode", "startTime", "endTime",
                 "energyKwh", "unitPrice", "durationMin", "amount", "status"},
    # 前端 Types.ets: RealTimeChargingData
    "RealtimeOut": {"voltage", "current", "powerKw", "durationSec", "energyKwh", "estimatedCost"},
    "StartOrderRequest": {"pileId"},
    # D 域（刘薇·feat/d-orders）新增映射（设计文档 §5.5/§5.6）
    "Envelope": {"success", "errorCode", "message", "data"},
    "UserSettingsOut": {"autoStop", "stopEnergyKwh", "stopThreshold"},
    "UserSettingsUpdate": {"autoStop", "stopEnergyKwh", "stopThreshold"},
    "OrderPage": {"items", "page", "size", "total"},
    "ScanResolveRequest": {"code"},
    "DailyStatsOut": {"date", "totalEnergyKwh", "totalAmount", "orderCount"},
}


def _alias_keys(model) -> set[str]:
    return {f.alias or name for name, f in model.model_fields.items()}


def test_model_field_contracts():
    models = {
        "UserOut": UserOut, "TokenResult": TokenResult,
        "RegisterRequest": RegisterRequest, "LoginRequest": LoginRequest,
        "PileOut": PileOut, "StationOut": StationOut,
        "OrderOut": OrderOut, "RealtimeOut": RealtimeOut,
        "StartOrderRequest": StartOrderRequest,
        "Envelope": Envelope,
        "UserSettingsOut": UserSettingsOut, "UserSettingsUpdate": UserSettingsUpdate,
        "OrderPage": OrderPage,
        "ScanResolveRequest": ScanResolveRequest, "DailyStatsOut": DailyStatsOut,
    }
    assert set(models) == set(EXPECTED_KEYS)
    for name, model in models.items():
        actual = _alias_keys(model)
        assert actual == EXPECTED_KEYS[name], f"{name} 字段漂移: {actual ^ EXPECTED_KEYS[name]}"


def test_password_never_serialized():
    """UserOut 必须不含任何密码形态字段（防泄露红线）。"""
    for key in _alias_keys(UserOut) | set(UserOut.model_fields):
        assert "password" not in key.lower() and "hash" not in key.lower()
