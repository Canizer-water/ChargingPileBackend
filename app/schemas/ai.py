"""AI 大模型问答契约（火山方舟 Ark DeepSeek 代理，密钥仅在后端 .env）。"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from app.schemas.common import CamelModel

MessageRole = Literal["system", "user", "assistant"]


class ChatMessage(CamelModel):
    role: MessageRole
    content: str


class ChatRequest(CamelModel):
    """与前端 LLMAgent 对齐：messages 携带多轮上下文；参数可选（camelCase）。"""

    messages: list[ChatMessage] = Field(min_length=1)
    max_tokens: int = Field(default=512, ge=1, le=4096)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class ChatUsage(CamelModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(CamelModel):
    reply: str
    model: str
    usage: ChatUsage | None = None


class PlateRequest(CamelModel):
    """车牌识别请求：图片以 data URL 形式上送（含 MIME 与 base64 内容）。"""

    image_data_url: str = Field(min_length=20, max_length=12_000_000)

    @field_validator("image_data_url")
    @classmethod
    def _validate_image_data_url(cls, v: str) -> str:
        if not (v.startswith("data:image/") and ";base64," in v):
            raise ValueError("imageDataUrl 必须是 data:image/...;base64,... 格式")
        return v


class PlateResponse(CamelModel):
    """车牌识别结果：未识别到清晰车牌时 plateNumber 为空字符串。"""

    plate_number: str = ""
    confidence: float = 0.0
    raw_text: str = ""
    model: str = ""
