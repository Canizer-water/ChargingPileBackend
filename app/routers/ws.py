"""B1 WebSocket 实时推送：订阅本人进行中充电会话，每秒推一帧 RealtimeOut（camelCase）。

路径：/api/v1/ws/charging/session/{session_id}
鉴权：query ?token=<access token>，或连接后首条消息发送 {"token": "..."}。
结束条件：会话 FINISHED / 用户停止 / 连接断开。
数据来源与 GET /charging/current 同一 provider（services/realtime.py），两路口径一致。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.security import decode_access_token
from app.core.timeutil import utc_now
from app.db import get_session_factory
from app.models.order import ChargingOrder, OrderStatus
from app.models.pile import Pile
from app.models.user import User
from app.services.realtime import get_provider

router = APIRouter()

#: WebSocket 业务关闭码（3000-4999 私有段）
CLOSE_UNAUTHORIZED = 4401
CLOSE_SESSION_NOT_FOUND = 4404


def _error_frame(code: int, detail: str) -> dict[str, Any]:
    return {"type": "error", "code": code, "detail": detail}


def _finished_frame(session_id: str) -> dict[str, Any]:
    return {"type": "session_finished", "sessionId": session_id}


async def _first_message_token(websocket: WebSocket) -> str | None:
    """query 无 token 时读取首条消息，兼容 {"token": "..."} 或纯文本 token。"""
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=3.0)
    except (WebSocketDisconnect, TimeoutError):
        return None
    if not raw:
        return None
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict) and payload.get("token"):
            return str(payload["token"])
    except json.JSONDecodeError:
        pass
    return raw.strip() or None


@router.websocket("/ws/charging/session/{session_id}")
async def ws_charging_session(websocket: WebSocket, session_id: str) -> None:
    """鉴权并校验归属后，以 1s 间隔推送本人进行中会话的实时帧。"""
    await websocket.accept()

    token = websocket.query_params.get("token") or await _first_message_token(websocket)
    if not token:
        await websocket.send_json(_error_frame(401, "未登录或登录状态已失效"))
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return

    user_id = decode_access_token(token)
    if user_id is None:
        await websocket.send_json(_error_frame(401, "未登录或登录状态已失效"))
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return

    async def _resolve(order_id: str) -> ChargingOrder | None:
        """库内确认订单属于本人且进行中；不存在/越权/已结束返回 None。"""
        async with get_session_factory()() as db:
            user = await db.get(User, user_id)
            if user is None:
                raise PermissionError
            result = await db.execute(
                select(ChargingOrder).where(
                    ChargingOrder.id == order_id,
                    ChargingOrder.user_id == user_id,
                    ChargingOrder.status == OrderStatus.CHARGING.value,
                )
            )
            return result.scalar_one_or_none()

    async def _send(order: ChargingOrder) -> None:
        async with get_session_factory()() as db:
            pile = (await db.execute(select(Pile).where(Pile.code == order.pile_code))).scalar_one_or_none()
            if pile is None:
                raise LookupError("桩档案缺失，无法提供实时数据")
            snapshot = get_provider().snapshot(order, pile, utc_now())
            await websocket.send_json(snapshot.model_dump(by_alias=True))

    try:
        session = await _resolve(session_id)
    except PermissionError:
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return

    # 首帧校验：无本人进行中会话 → 404 语义拒绝，不泄露存在性
    if session is None:
        await websocket.send_json(_error_frame(404, "没有进行中的充电会话"))
        await websocket.close(code=CLOSE_SESSION_NOT_FOUND)
        return

    try:
        await _send(session)
    except LookupError:
        await websocket.send_json(_error_frame(409, "桩档案缺失，无法提供实时数据"))
        await websocket.close(code=CLOSE_SESSION_NOT_FOUND)
        return

    while True:
        try:
            await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
            continue  # 忽略客户端后续业务消息；超时即到推送节拍
        except TimeoutError:
            pass
        except WebSocketDisconnect:
            return

        try:
            session = await _resolve(session_id)
            if session is None:
                await websocket.send_json(_finished_frame(session_id))
                await websocket.close(code=1000)
                return
            await _send(session)
        except PermissionError:
            await websocket.close(code=CLOSE_UNAUTHORIZED)
            return
        except LookupError:
            await websocket.send_json(_error_frame(409, "桩档案缺失，无法提供实时数据"))
            await websocket.close(code=CLOSE_SESSION_NOT_FOUND)
            return
