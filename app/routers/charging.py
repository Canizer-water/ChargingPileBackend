"""充电会话端点：start / current / stop（设计文档 §5.3）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.charging import RealtimeOut, StartOrderRequest
from app.schemas.order import OrderOut, order_to_out
from app.services.charging import current_realtime, start_order, stop_order

router = APIRouter(prefix="/charging", tags=["charging"])


@router.post("/start", status_code=201, response_model=OrderOut)
async def start(body: StartOrderRequest, db: AsyncSession = Depends(get_db),
                user: User = Depends(get_current_user)) -> OrderOut:
    return order_to_out(await start_order(db, user.id, body.pile_id))


@router.get("/current", response_model=RealtimeOut)
async def current(db: AsyncSession = Depends(get_db),
                  user: User = Depends(get_current_user)) -> RealtimeOut:
    _, snap = await current_realtime(db, user.id)
    return snap


@router.post("/{order_id}/stop", response_model=OrderOut)
async def stop(order_id: str, db: AsyncSession = Depends(get_db),
               user: User = Depends(get_current_user)) -> OrderOut:
    return order_to_out(await stop_order(db, user.id, order_id))
