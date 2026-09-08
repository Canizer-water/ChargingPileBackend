"""订单端点：list(分页) / detail，按用户隔离（设计文档 §5.4）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.order import ChargingOrder
from app.models.user import User
from app.schemas.common import Envelope, ok
from app.schemas.order import OrderOut, OrderPage, order_to_out

router = APIRouter(prefix="/orders", tags=["orders"])

_VALID_STATUS = {"CHARGING", "FINISHED"}


@router.get("", response_model=Envelope[OrderPage])
async def list_orders(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=50),
    order_status: str | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Envelope[OrderPage]:
    conditions = [ChargingOrder.user_id == user.id]
    if order_status is not None:
        if order_status not in _VALID_STATUS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="status 非法的订单状态")
        conditions.append(ChargingOrder.status == order_status)

    total = (await db.execute(
        select(func.count()).select_from(ChargingOrder).where(*conditions)
    )).scalar_one()

    result = await db.execute(
        select(ChargingOrder).where(*conditions)
        .order_by(ChargingOrder.start_time.desc(), ChargingOrder.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    items = [order_to_out(o) for o in result.scalars().all()]
    return ok(OrderPage(items=items, page=page, size=size, total=total))


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(order_id: str, db: AsyncSession = Depends(get_db),
                    user: User = Depends(get_current_user)) -> OrderOut:
    order = await db.get(ChargingOrder, order_id)
    # 越权与不存在同回 404（§6）
    if order is None or order.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订单不存在")
    return order_to_out(order)
