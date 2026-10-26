# Project LUMI — HTTP API v0.1

Base URL：`http(s)://<server>/api/v1`

## 认证

除「公开端点」外，所有请求必须携带：

```
X-LUMI-TOKEN: <LUMI_ACCESS_TOKEN>
```

也接受 `Authorization: Bearer <token>`。

**公开端点（无需令牌）**：`GET /`、`GET /api/v1/health`、`GET /api/v1/persona`

开发模式（`LUMI_ENV=dev` 且未配置 token）下不校验；生产模式强制校验，
否则后端拒绝启动。

## 错误信封

所有 4xx/5xx 统一返回：

```json
{
  "error": {
    "code": "upstream_timeout",
    "message": "模型响应超时，请重试。",
    "hint": "上游未在超时时间内返回完整结果。"
  }
}
```

响应头附带 `X-LUMI-Error-Code`。限流响应带 `Retry-After`（秒）。

| code | HTTP | 含义 |
|------|------|------|
| `unauthorized` | 401 | 客户端令牌缺失/错误 |
| `rate_limited` | 429 | 触发后端限流 |
| `empty_message` | 400 | 消息为空 |
| `provider_not_configured` | 503 | 后端未配置模型 Key（不返回假回复） |
| `upstream_unavailable` | 503 | 无法连接模型服务 |
| `upstream_timeout` | 504 | 模型响应超时 |
| `upstream_unauthorized` | 502 | 模型 Key 无效/被禁用 |
| `upstream_rate_limited` | 429 | 模型服务限流 |
| `upstream_bad_response` | 502 | 模型返回无法解析 |
| `not_found` | 404 | 会话不存在 |

---

## 系统

### GET /api/v1/health

设置页「连接状态」数据源。

```json
{
  "status": "ok",
  "version": "0.1.0",
  "env": "dev",
  "database": "ok",
  "provider": "deepseek",
  "provider_model": "deepseek-chat",
  "provider_configured": false,
  "api_key_hint": "sk-1...abcd",
  "auth_required": false
}
```

`api_key_hint` 为脱敏指纹，**永远不会**返回完整密钥。

### GET /api/v1/persona

AI 少女的名称与形象信息。

```json
{
  "name": "LUMI",
  "tagline": "会一直在你身边的 AI 少女",
  "avatar": "lumi_avatar",
  "greeting": "嗨，我是 LUMI。今天想聊点什么？"
}
```

### GET /api/v1/time

`{"server_time": "2026-10-26T15:30:00.123456+00:00"}`

## 聊天

### POST /api/v1/chat

请求：

```json
{
  "message": "你好，LUMI",
  "conversation_id": null
}
```

`conversation_id` 为 `null` 时新建会话；传已有 ID 则继续该会话。

响应 200：

```json
{
  "conversation_id": "9f2c…",
  "user_message_id": "a1…",
  "assistant_message_id": "b2…",
  "reply": "嗨！今天过得怎么样？",
  "model": "deepseek-chat",
  "latency_ms": 812
}
```

约束：`message` 1–8000 字符；`chat` 作用域限流默认 10 次/分钟/IP。

## 会话与历史

### GET /api/v1/conversations

```json
[
  {"id": "9f2c…", "title": "你好，LUMI", "created_at": "…", "updated_at": "…", "message_count": 2}
]
```

按 `updated_at` 降序，最多 50 条。

### POST /api/v1/conversations

可选 query `conversation_id`；201 返回 `{"id": "…", "title": "新的对话"}`。

### GET /api/v1/conversations/{id}/messages

查询参数 `limit`（1–2000，默认 500）。按时间升序返回：

```json
[
  {"id": "a1…", "conversation_id": "9f2c…", "role": "user", "content": "你好",
   "status": "ok", "model": null, "error_code": null, "latency_ms": null,
   "created_at": "2026-10-26T15:30:00.123456+00:00"}
]
```

### DELETE /api/v1/conversations/{id}

204 成功（级联删除消息）；404 不存在。

---

## 限流默认值

| 作用域 | 覆盖端点 | 默认 |
|--------|---------|------|
| `chat` | POST /chat | 10 次/分钟/IP |
| `default` | conversations 系列 | 30 次/分钟/IP |

通过 `LUMI_CHAT_RATE_LIMIT_PER_MINUTE` / `LUMI_RATE_LIMIT_PER_MINUTE` 调整。
