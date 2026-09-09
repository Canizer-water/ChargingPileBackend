"""AI 大模型代理：后端持 Key 转发火山方舟 Ark（对话模型 + 视觉识别）。

前端永不接触密钥；多轮上下文由前端维护、随 messages 上送；
system 提示由后端注入当前用户充电/桩状态，使快捷问答（充了多久/桩状态）有真实数据。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.timeutil import utc_now
from app.models.order import ChargingOrder, OrderStatus
from app.models.pile import Pile
from app.schemas.ai import ChatRequest, ChatResponse, ChatUsage, PlateRequest, PlateResponse
from app.schemas.common import fmt_datetime
from app.services.charging import BizError
from app.services.realtime import get_provider

logger = logging.getLogger(__name__)


async def build_device_context(db: AsyncSession, user_id: str) -> str:
    """当前用户充电/订单状态文本，注入 system prompt（对齐前端 DeviceState）。"""
    lines: list[str] = []
    active = await db.execute(
        select(ChargingOrder)
        .where(ChargingOrder.user_id == user_id,
               ChargingOrder.status == OrderStatus.CHARGING.value)
        .order_by(ChargingOrder.start_time.desc())
        .limit(1)
    )
    order = active.scalar_one_or_none()
    if order is not None:
        pile = (await db.execute(select(Pile).where(Pile.code == order.pile_code))).scalar_one_or_none()
        if pile is not None:
            snap = get_provider().snapshot(order, pile, utc_now())
            lines.append(
                f"- 正在充电：桩 {order.pile_code}，已充 {snap.duration_sec:.0f} 秒，"
                f"功率 {snap.power_kw:.1f}kW，电压 {snap.voltage:.1f}V，电流 {snap.current:.1f}A，"
                f"电量 {snap.energy_kwh:.2f}kWh，预估费用 {snap.estimated_cost:.2f} 元"
            )
    recent = await db.execute(
        select(ChargingOrder)
        .where(ChargingOrder.user_id == user_id,
               ChargingOrder.status == OrderStatus.FINISHED.value)
        .order_by(ChargingOrder.end_time.desc())
        .limit(1)
    )
    done = recent.scalar_one_or_none()
    if done is not None:
        lines.append(
            f"- 最近一次充电：桩 {done.pile_code}，{fmt_datetime(done.start_time)} 至 "
            f"{fmt_datetime(done.end_time)}，电量 {done.energy_kwh:.2f}kWh，费用 {done.amount:.2f} 元"
        )
    return "\n".join(lines)


def _system_prompt(context: str) -> str:
    base = (
        "你是智能充电桩平台的 AI 助手，请用中文简洁回答用户关于充电、订单、设备状态的问题。"
        "只能依据下方提供的真实状态回答；不确定的内容请明确说明，不要编造。"
    )
    return f"{base}\n当前用户状态：\n{context}" if context else base


_PLATE_PROMPT = (
    "请识别这张图片中的中国机动车车牌号。只输出 JSON："
    '{"plateNumber": "京A12345"}；如果图片中没有清晰可辨认的车牌，'
    '输出 {"plateNumber": null}。不要输出任何其他内容。'
)

_PLATE_RE = re.compile(
    r"[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼使领]"
    r"[A-HJ-NP-Z][A-HJ-NP-Z0-9]{5,6}[挂学警港澳]?"
)


def _parse_plate(raw: str) -> tuple[str, float]:
    """从模型输出提取车牌与置信度：优先 JSON，失败用正则兜底。"""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip()).strip()
    try:
        obj = json.loads(text)
        plate = obj.get("plateNumber") or obj.get("plate_number") or ""
        confidence = float(obj.get("confidence") or 0.0)
        return str(plate).strip(), max(0.0, min(confidence, 1.0))
    except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
        pass
    match = _PLATE_RE.search(raw)
    if match:
        return match.group(0), 0.0
    return raw.strip().strip('"“”`'), 0.0


async def recognize_plate(request: PlateRequest) -> PlateResponse:
    settings = get_settings()
    if not settings.ark_api_key:
        raise BizError(503, "AI 服务未配置：请在 .env 填写 ARK_API_KEY")
    if not settings.ark_vision_model:
        raise BizError(503, "AI 服务未配置：请在 .env 填写 ARK_VISION_MODEL")

    payload: dict[str, Any] = {
        "model": settings.ark_vision_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _PLATE_PROMPT},
                    {"type": "image_url", "image_url": {"url": request.image_data_url}},
                ],
            }
        ],
        "max_tokens": 256,
        "temperature": 0.1,
        "stream": False,
    }
    url = f"{settings.ark_base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.ark_api_key}"}

    try:
        async with httpx.AsyncClient(timeout=settings.ai_request_timeout_sec) as client:
            resp = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning("ark plate request failed: %s", exc)
        raise BizError(502, "AI 服务暂时不可用，请稍后重试") from exc

    if resp.status_code == 402:
        raise BizError(402, "AI 账户余额或可用调用额度耗尽")
    if resp.status_code >= 400:
        logger.warning("ark plate error %s: %s", resp.status_code, resp.text[:300])
        raise BizError(502, "AI 服务返回异常，请稍后重试")

    try:
        data = resp.json()
        raw = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        logger.warning("ark plate unexpected payload: %s", resp.text[:300])
        raise BizError(502, "AI 服务响应格式异常") from exc

    plate, confidence = _parse_plate(raw)
    return PlateResponse(
        plate_number=plate,
        confidence=confidence,
        raw_text=raw.strip()[:500],
        model=data.get("model") or settings.ark_vision_model,
    )


async def chat_completion(db: AsyncSession, user_id: str, request: ChatRequest) -> ChatResponse:
    settings = get_settings()
    if not settings.ark_api_key:
        raise BizError(503, "AI 服务未配置：请在 .env 填写 ARK_API_KEY")
    if not settings.ark_model:
        raise BizError(503, "AI 服务未配置：请在 .env 填写 ARK_MODEL")

    context = await build_device_context(db, user_id)
    messages: list[dict[str, str]] = [{"role": "system", "content": _system_prompt(context)}]
    # 前端可能自带 system（旧版直连逻辑），以后端注入的实时状态为准，避免重复
    messages += [{"role": m.role, "content": m.content} for m in request.messages if m.role != "system"]

    payload: dict[str, Any] = {
        "model": settings.ark_model,
        "messages": messages,
        "max_tokens": request.max_tokens,
        "temperature": request.temperature,
        "stream": False,
    }
    url = f"{settings.ark_base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.ark_api_key}"}

    try:
        async with httpx.AsyncClient(timeout=settings.ai_request_timeout_sec) as client:
            resp = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning("ark request failed: %s", exc)
        raise BizError(502, "AI 服务暂时不可用，请稍后重试") from exc

    if resp.status_code == 402:
        raise BizError(402, "AI 账户余额或可用调用额度耗尽")
    if resp.status_code >= 400:
        logger.warning("ark error %s: %s", resp.status_code, resp.text[:300])
        raise BizError(502, "AI 服务返回异常，请稍后重试")

    try:
        data = resp.json()
        reply = data["choices"][0]["message"]["content"]
        usage_raw = data.get("usage") or {}
        usage = ChatUsage(
            prompt_tokens=usage_raw.get("prompt_tokens", 0),
            completion_tokens=usage_raw.get("completion_tokens", 0),
            total_tokens=usage_raw.get("total_tokens", 0),
        )
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        logger.warning("ark unexpected payload: %s", resp.text[:300])
        raise BizError(502, "AI 服务响应格式异常") from exc

    return ChatResponse(reply=reply, model=data.get("model") or settings.ark_model, usage=usage)
