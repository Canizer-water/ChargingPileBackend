"""Pydantic 基类：JSON 一律 camelCase，与前端 Types.ets 逐字对齐（设计文档 §1.1）。"""

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

T = TypeVar("T")


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


def fmt_datetime(dt: datetime | None) -> str:
    """时间口径与前端本地实现一致：'YYYY-MM-DD HH:MM:SS'，空值回退 ''。"""
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


class Envelope(CamelModel, Generic[T]):
    """统一成功响应包（设计文档 §5.6）：success/errorCode/message/data。

    错误仍由全局异常处理器返回 {"detail"}，由前端 HTTP 层映射为 {success, message}。
    """

    success: bool = True
    error_code: int = 0
    message: str = "ok"
    data: T | None = None


def ok(data: T, message: str = "ok") -> Envelope[T]:
    """成功响应便捷构造。"""
    return Envelope(success=True, error_code=0, message=message, data=data)
