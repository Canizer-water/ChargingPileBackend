"""扫码兜底端点（设计文档 §5.5，Story 9）：POST /scan/resolve。

复用 GET /piles/by-code 的桩码解析逻辑，仅改为 Envelope<T> 包装。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.common import Envelope, ok
from app.schemas.scan import ScanResolveRequest
from app.schemas.station import PileOut
from app.services.charging import BizError, find_pile_by_code

router = APIRouter(prefix="/scan", tags=["scan"])


@router.post("/resolve", response_model=Envelope[PileOut])
async def resolve(body: ScanResolveRequest, db: AsyncSession = Depends(get_db),
                  _: User = Depends(get_current_user)) -> Envelope[PileOut]:
    pile = await find_pile_by_code(db, body.code)
    if pile is None:
        raise BizError(404, "充电桩不存在")
    return ok(PileOut.model_validate(pile))
