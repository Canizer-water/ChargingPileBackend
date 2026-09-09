"""IoTDA 应用侧：IAM token + 设备影子查询（只读拉取，供 device_bridge 收端用）。

影子语义：设备 MQTT 上报属性 → IoTDA 按 service 缓存到设备影子；应用侧用
AK/SK 换 X-Auth-Token 后 `GET .../shadow` 拉取。仅后端持有 AK/SK，绝不下发前端。
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request

from app.core.config import get_settings
from app.schemas.charging import RealtimeOut

logger = logging.getLogger(__name__)

#: IAM token 有效期保守值（秒）；到期/401 时重取
_TOKEN_TTL_SEC = 3600.0

_cached_token: str = ""
_cached_at: float = 0.0


def extract_properties(shadow: list[dict], service_id: str) -> dict | None:
    """从影子响应 `shadow[]` 中取指定 service 的 `reported.properties`。"""
    for item in shadow or []:
        if item.get("service_id") == service_id:
            props = (item.get("reported") or {}).get("properties")
            return props if isinstance(props, dict) else None
    return None


def _as_num(props: dict, *keys: str) -> float:
    for k in keys:
        v = props.get(k)
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str) and v.strip() and v.strip().replace("-", "", 1).replace(".", "", 1).isdigit():
            return float(v)
    return 0.0


def properties_to_realtime(props: dict, unit_price: float = 0.0) -> RealtimeOut:
    """影子属性（数值或数字字符串）→ RealtimeOut；费用未给时按电量×单价估算。"""
    energy_kwh = _as_num(props, "energyKwh", "energy_kwh")
    estimated = _as_num(props, "estimatedCost", "estimated_cost")
    if estimated <= 0:
        estimated = round(energy_kwh * unit_price, 2)
    return RealtimeOut(
        voltage=_as_num(props, "voltage"),
        current=_as_num(props, "current"),
        power_kw=_as_num(props, "powerKw", "power_kw"),
        duration_sec=_as_num(props, "durationSec", "duration_sec"),
        energy_kwh=energy_kwh,
        estimated_cost=estimated,
    )


def _fetch_token() -> str:
    settings = get_settings()
    body = {
        "auth": {
            "identity": {
                "methods": ["hw_ak_sk"],
                "hw_ak_sk": {
                    "access": {"key": settings.iotda_ak},
                    "secret": {"key": settings.iotda_sk},
                },
            },
            "scope": {"project": {"id": settings.iotda_project_id}},
        }
    }
    url = f"https://iam.{settings.iotda_region}.myhuaweicloud.com/v3/auth/tokens"
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        token = resp.headers.get("x-subject-token") or resp.headers.get("X-Subject-Token")
    if not token:
        raise RuntimeError("IAM 未返回 x-subject-token")
    return token


def _ensure_token(force: bool = False) -> str:
    global _cached_token, _cached_at
    if not force and _cached_token and time.time() - _cached_at < _TOKEN_TTL_SEC:
        return _cached_token
    _cached_token = _fetch_token()
    _cached_at = time.time()
    return _cached_token


def query_shadow_properties(device_id: str) -> dict | None:
    """查询单台设备影子属性；网络/鉴权失败返回 None（调用方跳过即可）。"""
    settings = get_settings()
    url = (
        f"{settings.iotda_endpoint.rstrip('/')}"
        f"/v5/iot/{settings.iotda_project_id}/devices/{device_id}/shadow"
    )

    def _do(token: str) -> dict | None:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"X-Auth-Token": token}), timeout=15
        ) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        return extract_properties(data.get("shadow") or [], settings.iotda_service_id)

    try:
        return _do(_ensure_token())
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            try:
                return _do(_ensure_token(force=True))
            except Exception:  # noqa: BLE001
                logger.exception("IoTDA 影子查询(刷新 token)失败 device=%s", device_id)
                return None
        logger.warning("IoTDA 影子查询 HTTP %s device=%s body=%s", exc.code, device_id,
                       exc.read(200).decode("utf-8", "replace"))
        return None
    except Exception:  # noqa: BLE001 - 网络抖动由调用方按缺数据回退处理
        logger.warning("IoTDA 影子查询异常 device=%s", device_id, exc_info=True)
        return None
