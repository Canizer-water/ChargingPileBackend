from __future__ import annotations

from app.schemas.common import CamelModel


class ScanResolveRequest(CamelModel):
    """扫码兜底请求（设计文档 §5.5）。"""

    code: str
