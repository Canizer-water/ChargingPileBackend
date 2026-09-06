"""Pydantic 基类：JSON 一律 camelCase，与前端 Types.ets 逐字对齐（设计文档 §1.1）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


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
