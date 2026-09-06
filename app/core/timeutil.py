"""统一时间口径：全库使用 naive UTC（SQLite 无时区列），出口格式化见 schemas.fmt_datetime。"""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
