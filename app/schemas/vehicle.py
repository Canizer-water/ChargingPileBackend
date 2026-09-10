"""车辆模型（C 域 · Story 4），与前端 Vehicle DTO 逐字对齐（设计文档 §5.7）。"""

from __future__ import annotations

import re

from pydantic import field_validator

from app.schemas.common import CamelModel

#: 无车辆记录时的默认值（设计文档 §5.7）
DEFAULT_PLATE_NO = ""
DEFAULT_BATTERY = 75
DEFAULT_RANGE_KM = 260

#: 车牌号长度上限（与表列 String(16) 一致）
PLATE_MAX_LEN = 16
#: 归一化后允许的最短长度（民用车牌 7 位、跨境/缩写等允许 5 位起）
PLATE_MIN_LEN = 5
#: 归一化后仅允许汉字、大写英文字母、数字（汉字取 CJK 基本区 U+4E00–U+9FA5）
_PLATE_ALLOWED = re.compile(r"^[一-龥A-Z0-9]+$")
#: 归一化阶段剔除的分隔符
_PLATE_SEPARATORS = "·．.-"


def normalize_plate(raw: str) -> str:
    """车牌归一化：去空白、去分隔符、字母转大写（设计文档 §5.7）。

    识别接口（``POST /ai/plate``）常返回 ``陕A·12345`` 这类带空格/圆点的结果，
    归一后入库可避免同一车牌出现多种写法。
    """
    no_space = re.sub(r"\s+", "", raw)
    stripped = "".join(ch for ch in no_space if ch not in _PLATE_SEPARATORS)
    return stripped.upper()


def is_valid_plate(plate: str) -> bool:
    """校验**已归一化**的车牌：长度为空（清除）或 5–16 位汉字/字母/数字。

    由 router 抛出 ``BizError(422)`` 而非在 schema 内 raise，是为了让错误体保持
    FastAPI ``{"detail": "字符串"}`` 形状——前端 HTTP 层按 detail 字符串映射提示文案。
    """
    if plate == "":
        return True
    return PLATE_MIN_LEN <= len(plate) <= PLATE_MAX_LEN and bool(_PLATE_ALLOWED.match(plate))


class VehicleOut(CamelModel):
    plate_no: str
    battery: int
    range_km: int


class VehicleUpdate(CamelModel):
    """``PUT /vehicle/current`` 请求体（设计文档 §5.7）。

    ``plate_no`` 在此仅做归一化，格式合法性由 router 判定（见 :func:`is_valid_plate`）；
    归一后为空串表示清除车牌。
    """

    plate_no: str = DEFAULT_PLATE_NO

    @field_validator("plate_no")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return normalize_plate(v)


def default_vehicle_out() -> VehicleOut:
    return VehicleOut(
        plate_no=DEFAULT_PLATE_NO,
        battery=DEFAULT_BATTERY,
        range_km=DEFAULT_RANGE_KM,
    )
