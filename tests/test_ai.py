"""AI 大模型代理契约/行为测试（火山方舟 Ark 上游一律 mock，不真实联网）。"""

from __future__ import annotations

import json

from tests.conftest import API, bearer
from tests.test_stations import pick_idle_pile


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = json.dumps(self._payload, ensure_ascii=False)

    def json(self) -> dict:
        return self._payload


def _ok_post(captured: dict):
    async def post(self, url: str, *, json=None, headers=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _FakeResponse(200, {
            "id": "chatcmpl-fake",
            "model": "deepseek-v3-250324",
            "choices": [{"message": {"role": "assistant", "content": "模拟回答"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        })
    return post


def _fail_post(captured: dict, status_code: int):
    async def post(self, url: str, *, json=None, headers=None):
        captured["json"] = json
        return _FakeResponse(status_code, {"error": {"message": "boom"}})
    return post


PLATE_IMG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _plate_ok_post(captured: dict, content: str | None = None):
    async def post(self, url: str, *, json=None, headers=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _FakeResponse(200, {
            "id": "chatcmpl-plate-fake",
            "model": "doubao-1-5-vision-pro-32k-250115",
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": content or '{"plateNumber": "京A12345", "confidence": 0.98}',
                }
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
        })
    return post


def test_plate_requires_auth(client):
    assert client.post(f"{API}/ai/plate", json={"imageDataUrl": PLATE_IMG}).status_code == 401


def test_plate_without_api_key_503(client, auth, monkeypatch):
    settings = __import__("app.core.config", fromlist=["get_settings"]).get_settings()
    monkeypatch.setattr(settings, "ark_api_key", "")
    res = client.post(
        f"{API}/ai/plate",
        json={"imageDataUrl": PLATE_IMG},
        headers=bearer(auth["token"]),
    )
    assert res.status_code == 503
    assert "ARK_API_KEY" in res.json()["detail"]


def test_plate_without_vision_model_503(client, auth, monkeypatch):
    settings = __import__("app.core.config", fromlist=["get_settings"]).get_settings()
    monkeypatch.setattr(settings, "ark_api_key", "test-key")
    monkeypatch.setattr(settings, "ark_vision_model", "")
    res = client.post(
        f"{API}/ai/plate",
        json={"imageDataUrl": PLATE_IMG},
        headers=bearer(auth["token"]),
    )
    assert res.status_code == 503
    assert "ARK_VISION_MODEL" in res.json()["detail"]


def test_plate_rejects_non_data_url(client, auth):
    res = client.post(
        f"{API}/ai/plate",
        json={"imageDataUrl": "http://example.com/plate.jpg"},
        headers=bearer(auth["token"]),
    )
    assert res.status_code == 422


def test_plate_success_and_forward_payload(client, auth, monkeypatch):
    settings = __import__("app.core.config", fromlist=["get_settings"]).get_settings()
    monkeypatch.setattr(settings, "ark_api_key", "test-key")
    monkeypatch.setattr(settings, "ark_vision_model", "test-vision-model")
    captured: dict = {}
    monkeypatch.setattr(
        "app.services.ai.httpx.AsyncClient.post", _plate_ok_post(captured)
    )
    res = client.post(
        f"{API}/ai/plate",
        json={"imageDataUrl": PLATE_IMG},
        headers=bearer(auth["token"]),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    assert body["errorCode"] == 0
    assert body["data"]["plateNumber"] == "京A12345"
    assert body["data"]["confidence"] == 0.98

    payload = captured["json"]
    assert payload["model"] == settings.ark_vision_model
    content = payload["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"] == PLATE_IMG
    assert "Bearer" in captured["headers"]["Authorization"]


def test_plate_plain_text_fallback(client, auth, monkeypatch):
    settings = __import__("app.core.config", fromlist=["get_settings"]).get_settings()
    monkeypatch.setattr(settings, "ark_api_key", "test-key")
    monkeypatch.setattr(settings, "ark_vision_model", "test-vision-model")
    captured: dict = {}
    monkeypatch.setattr(
        "app.services.ai.httpx.AsyncClient.post",
        _plate_ok_post(captured, content="识别到车牌：粤B88888"),
    )
    res = client.post(
        f"{API}/ai/plate",
        json={"imageDataUrl": PLATE_IMG},
        headers=bearer(auth["token"]),
    )
    assert res.status_code == 200
    assert res.json()["data"]["plateNumber"] == "粤B88888"


def test_plate_402_maps_to_biz_error(client, auth, monkeypatch):
    settings = __import__("app.core.config", fromlist=["get_settings"]).get_settings()
    monkeypatch.setattr(settings, "ark_api_key", "test-key")
    monkeypatch.setattr(settings, "ark_vision_model", "test-vision-model")
    captured: dict = {}
    monkeypatch.setattr(
        "app.services.ai.httpx.AsyncClient.post", _fail_post(captured, 402)
    )
    res = client.post(
        f"{API}/ai/plate",
        json={"imageDataUrl": PLATE_IMG},
        headers=bearer(auth["token"]),
    )
    assert res.status_code == 402


def test_chat_requires_auth(client):
    assert client.post(f"{API}/ai/chat", json={"messages": [{"role": "user", "content": "hi"}]}).status_code == 401


def test_chat_without_api_key_503(client, auth, monkeypatch):
    settings = __import__("app.core.config", fromlist=["get_settings"]).get_settings()
    monkeypatch.setattr(settings, "ark_api_key", "")
    res = client.post(
        f"{API}/ai/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers=bearer(auth["token"]),
    )
    assert res.status_code == 503
    assert "ARK_API_KEY" in res.json()["detail"]


def test_chat_without_model_503(client, auth, monkeypatch):
    settings = __import__("app.core.config", fromlist=["get_settings"]).get_settings()
    monkeypatch.setattr(settings, "ark_api_key", "test-key")
    monkeypatch.setattr(settings, "ark_model", "")
    res = client.post(
        f"{API}/ai/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers=bearer(auth["token"]),
    )
    assert res.status_code == 503
    assert "ARK_MODEL" in res.json()["detail"]


def test_chat_success_and_forward_payload(client, auth, monkeypatch):
    settings = __import__("app.core.config", fromlist=["get_settings"]).get_settings()
    monkeypatch.setattr(settings, "ark_api_key", "test-key")
    monkeypatch.setattr(settings, "ark_model", "test-chat-model")
    captured: dict = {}
    monkeypatch.setattr(
        "app.services.ai.httpx.AsyncClient.post", _ok_post(captured)
    )

    res = client.post(
        f"{API}/ai/chat",
        json={"messages": [{"role": "user", "content": "现在充了多久？"}], "maxTokens": 200},
        headers=bearer(auth["token"]),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    assert body["errorCode"] == 0
    assert body["message"] == "ok"
    assert body["data"]["reply"] == "模拟回答"
    assert body["data"]["model"] == "deepseek-v3-250324"
    assert body["data"]["usage"] == {"promptTokens": 10, "completionTokens": 5, "totalTokens": 15}

    # 转发上游：camelCase 请求被转成 OpenAI snake_case 参数；system 由后端注入
    payload = captured["json"]
    assert payload["max_tokens"] == 200
    assert payload["stream"] is False
    roles = [m["role"] for m in payload["messages"]]
    assert roles[0] == "system"
    assert "AI 助手" in payload["messages"][0]["content"]


def test_chat_402_maps_to_biz_error(client, auth, monkeypatch):
    settings = __import__("app.core.config", fromlist=["get_settings"]).get_settings()
    monkeypatch.setattr(settings, "ark_api_key", "test-key")
    monkeypatch.setattr(settings, "ark_model", "test-chat-model")
    captured: dict = {}
    monkeypatch.setattr(
        "app.services.ai.httpx.AsyncClient.post", _fail_post(captured, 402)
    )
    res = client.post(
        f"{API}/ai/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers=bearer(auth["token"]),
    )
    assert res.status_code == 402


def test_chat_injects_charging_context(client, auth, monkeypatch):
    """进行中会话时，system prompt 应带真实充电状态（快捷提问的数据来源）。"""
    settings = __import__("app.core.config", fromlist=["get_settings"]).get_settings()
    monkeypatch.setattr(settings, "ark_api_key", "test-key")
    monkeypatch.setattr(settings, "ark_model", "test-chat-model")
    headers = bearer(auth["token"])
    pile = pick_idle_pile(client, headers)
    order = client.post(f"{API}/charging/start", json={"pileId": pile["id"]}, headers=headers)
    assert order.status_code == 201
    try:
        captured: dict = {}
        monkeypatch.setattr(
            "app.services.ai.httpx.AsyncClient.post", _ok_post(captured)
        )
        res = client.post(
            f"{API}/ai/chat",
            json={"messages": [{"role": "user", "content": "充了多久？"}]},
            headers=headers,
        )
        assert res.status_code == 200
        system = captured["json"]["messages"][0]["content"]
        assert "正在充电" in system
        assert order.json()["pileCode"] in system
    finally:
        client.post(f"{API}/charging/{order.json()['id']}/stop", headers=headers)
