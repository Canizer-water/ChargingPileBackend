"""订单端点：list / detail，按用户隔离（设计文档 §5.4）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.order import ChargingOrder
from app.models.user import User
from app.schemas.order import OrderOut, order_to_out

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=list[OrderOut])
async def list_orders(db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)) -> list[OrderOut]:
    result = await db.execute(
        select(ChargingOrder).where(ChargingOrder.user_id == user.id)
        .order_by(ChargingOrder.start_time.desc(), ChargingOrder.id.desc())
    )
    return [order_to_out(o) for o in result.scalars().all()]


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(order_id: str, db: AsyncSession = Depends(get_db),
                    user: User = Depends(get_current_user)) -> OrderOut:
    order = await db.get(ChargingOrder, order_id)
    # 越权与不存在同回 404（§6）
    if order is None or order.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订单不存在")
    return order_to_out(order)
