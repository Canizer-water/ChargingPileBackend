"""AI 大模型问答端点（火山方舟 Ark DeepSeek 代理，需登录）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.ai import ChatRequest, ChatResponse, PlateRequest, PlateResponse
from app.schemas.common import Envelope, ok
from app.services.ai import chat_completion, recognize_plate

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/chat", response_model=Envelope[ChatResponse])
async def chat(body: ChatRequest, db: AsyncSession = Depends(get_db),
               user: User = Depends(get_current_user)) -> Envelope[ChatResponse]:
    return ok(await chat_completion(db, user.id, body))


@router.post("/plate", response_model=Envelope[PlateResponse])
async def plate(body: PlateRequest,
                user: User = Depends(get_current_user)) -> Envelope[PlateResponse]:
    return ok(await recognize_plate(body))
