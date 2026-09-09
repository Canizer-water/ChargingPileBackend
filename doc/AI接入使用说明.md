# AI 大模型接入使用说明（火山引擎方舟 Ark）

> 适用版本：`feat/b-realtime` 分支的 AI 模块（AI 助手对话 + AI 车牌识别）。
> 后端只做代理：密钥与模型配置全部放 `.env`，前端永不接触密钥。

## 一、功能清单

| 能力 | 接口 | 说明 |
| --- | --- | --- |
| AI 助手对话 | `POST /api/v1/ai/chat` | 多轮问答；后端自动注入当前充电状态到 system prompt |
| AI 车牌识别 | `POST /api/v1/ai/plate` | 上传图片（base64 data URL），调用视觉模型识别车牌 |

两个接口都需要登录（Bearer Token）。成功响应统一为 Envelope：

```json
{ "success": true, "errorCode": 0, "message": "ok", "data": { ... } }
```

## 二、配置步骤

1. 项目根目录有 `.env`（已被 `.gitignore` 忽略，不会提交）。如缺失，复制 `.env.example` 为 `.env`。
2. 填写以下内容：

```ini
ARK_API_KEY=你的火山方舟 API Key
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/coding/v3
ARK_MODEL=你账号可用的对话模型名或 ep-xxx 接入点 ID
ARK_VISION_MODEL=你账号可用的视觉模型名或接入点 ID（车牌识别用，必须支持图像输入）
AI_REQUEST_TIMEOUT_SEC=60
```

> 说明：
> - `ARK_MODEL` 与 `ARK_VISION_MODEL` 没有默认值，必须自己填。到火山方舟控制台查看你账号可用的模型 / 推理接入点。
> - 方舟既支持模型名（如 `deepseek-v3-250324`、doubao 系列），也支持推理接入点 ID（`ep-xxx`），两者填一个即可。
> - 车牌识别用的视觉模型必须支持图片输入；如果 `ARK_BASE_URL` 指向的端点（如 coding 端点）没有视觉模型，可将 `ARK_BASE_URL` 换成标准端点 `https://ark.cn-beijing.volces.com/api/v3`。
> - 环境变量优先级高于 `.env`：如果系统环境里已设 `ARK_API_KEY`，会优先使用系统里的值。

## 三、启动与测试

### 运行测试（不需要真实 Key，全部 mock 上游）

```powershell
# 只跑 AI 相关
.venv\Scripts\python.exe -m pytest tests\test_ai.py -v

# 全量
.venv\Scripts\python.exe -m pytest -q
```

预期：AI 相关 13 个用例全过，全量 46 个用例全过。

### 启动服务

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

打开 http://127.0.0.1:8000/docs 即可在线调试。

## 四、真实联调

1. 确认 `.env` 已填 `ARK_API_KEY`、`ARK_MODEL`、`ARK_VISION_MODEL`。
2. 启动服务，打开 `/docs`。
3. 先 `POST /auth/register`（或 `/auth/login`）拿 token，在 Swagger 右上角 Authorize 填入。

### 4.1 AI 助手对话

```json
{
  "messages": [
    { "role": "user", "content": "我现在充了多久？" }
  ],
  "maxTokens": 512,
  "temperature": 0.7
}
```

成功返回示例：

```json
{
  "success": true,
  "errorCode": 0,
  "message": "ok",
  "data": {
    "reply": "你已充电 320 秒……",
    "model": "你配置的模型名",
    "usage": { "promptTokens": 100, "completionTokens": 50, "totalTokens": 150 }
  }
}
```

### 4.2 车牌识别

把照片转成 base64 后拼成 data URL 上传：

```json
{
  "imageDataUrl": "data:image/jpeg;base64,/9j/4AAQ..."
}
```

成功返回示例：

```json
{
  "success": true,
  "errorCode": 0,
  "message": "ok",
  "data": {
    "plateNumber": "京A12345",
    "confidence": 0.98,
    "rawText": "模型原始输出（排查用）",
    "model": "你配置的视觉模型名"
  }
}
```

未识别到车牌时 `plateNumber` 为空字符串。前端拿到车牌后与用户绑定车牌比对（对应 `AICamera.ets`），匹配后的启动充电指令走 IoTDA/MQTT 下发，与本 AI 模块解耦。

## 五、常见报错对照

| 状态码 | 含义 | 处理方式 |
| --- | --- | --- |
| 503 `ARK_API_KEY` | Key 未配置 | `.env` 填 `ARK_API_KEY` |
| 503 `ARK_MODEL` | 对话模型未配置 | `.env` 填 `ARK_MODEL`（模型名或 ep-xxx） |
| 503 `ARK_VISION_MODEL` | 视觉模型未配置 | `.env` 填 `ARK_VISION_MODEL` |
| 401 | 未登录 / token 失效 | 重新注册或登录拿 token |
| 402 | 账号余额或调用额度耗尽 | 方舟控制台充值/调整额度 |
| 422 | 参数不合法 | 检查 `imageDataUrl` 必须是 `data:image/...;base64,...` 格式 |
| 502 | 上游服务异常/网络问题 | 检查 Key、模型名、接入点是否可用；看后端日志 |

## 六、代码结构

- `app/core/config.py`：`ark_*` 配置项（读取 `.env` / 环境变量）
- `app/schemas/ai.py`：`ChatRequest/ChatResponse`、`PlateRequest/PlateResponse` 契约
- `app/services/ai.py`：`chat_completion()`、`recognize_plate()`（调用方舟 chat/completions）
- `app/routers/ai.py`：`POST /ai/chat`、`POST /ai/plate`
- `tests/test_ai.py`：mock 上游的行为测试

