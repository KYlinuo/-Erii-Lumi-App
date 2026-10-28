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

---

# v0.2 新增接口（2026-10-28）

Base URL 不变：`http(s)://<server>/api/v1`。以下接口全部需要凭据
（主令牌或设备令牌），除 `/health`、`/persona`、`/time`。

## 设备

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/devices` | 注册设备，**一次性返回明文令牌**（`token`），需立刻存 Keychain |
| GET | `/devices` | 设备列表 |
| PATCH | `/devices/{id}` | 改名 |
| PUT | `/devices/{id}/scopes` | 设置作用域（`chat`/`sync`/`memory`/`world`/`admin`） |
| DELETE | `/devices/{id}` | 吊销，令牌立即失效 |
| GET | `/devices/me` | 当前令牌的身份与权限自检 |

服务端只存 `SHA256(token + LUMI_DEVICE_TOKEN_SECRET)`，库泄露也无法还原令牌。

## 人格

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/characters` | 人格列表（含 `source`，`reconstructed` 表示设定待补充） |
| GET | `/characters/{key}` | 人格详情（含 `system_prompt`） |
| GET | `/characters/{key}/idle-lines` | 待机台词，返回体带 `fictional: true` |
| PATCH | `/conversations/{id}/character?character_key=` | 切换会话人格 |

## 长期记忆

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/memory?character_key=&scope=&limit=` | 当前人格可见范围内的记忆 |
| GET | `/memory/summary` | 按类型统计 |
| GET | `/memory/export` | 导出（含来源与可信度） |
| POST | `/memory` | 新增（`{scope, content, character_id?, source_type?, salience?}`） |
| PATCH | `/memory/{id}` | 修改内容 / 可信度 / 状态 |
| POST | `/memory/{id}/archive` | 归档 |
| DELETE | `/memory/{id}` | 删除 |

`subject`=`user` 的记忆跨人格共享；`relationship` / `character` 按 `character_id` 隔离。

## 虚构人生

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/world/{key}/timeline?days=&kind=&limit=` | 时间线 |
| GET | `/world/{key}/diary` | 日记（带 `notice` 声明为虚构） |
| POST | `/world/{key}/simulate?max_events=&date=` | 生成某天的虚构生活（幂等） |
| GET | `/world/{key}/state` | 概览 |

所有事件 `simulated=true`：这是角色设定里的故事，**不是**用户真实经历。

## 跨设备同步

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/sync` | `{since:{conversation_id:conv_seq}, limit}` → 全会话增量 |
| GET | `/sync/conversation/{id}?after=&limit=` | 单会话增量 |
| PUT | `/sync/cursor` | 记录设备读到的位置 |
| GET | `/sync/cursor/{id}` | 读取设备游标 |
| DELETE | `/sync/messages/{id}` | 软删除（tombstone 会同步给另一端） |

消息在会话内有单调递增的 `conv_seq`；`request_id` 全局唯一用于幂等去重。

## 主动联系

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/proactive` | 待投递的主动消息 |
| POST | `/proactive/delivered` | 确认投递 `{ids:[...]}` |
| POST | `/proactive/plan` | 按时段/配额判断是否排一条 |
| POST | `/proactive/cancel` | 即时关闭：撤销所有未投递 |
| GET | `/proactive/status` | 策略与当前是否允许发送 |

`apns_remote_push=false`：采用**服务端排队 + 客户端拉取**，
未实现也不声称实现了 APNs 远程推送。

## 新增错误码

| code | HTTP | 含义 |
|---|---|---|
| `request_id_conflict` | 409 | 幂等 ID 已用于另一个会话 |
| `forbidden` | 403 | 设备令牌缺少所需 scope |
| `invalid_scope` | 422 | 记忆 scope 非法 |
| `invalid_date` | 422 | 日期格式应为 YYYY-MM-DD |

## /health 新增字段

`schema_version`、`is_mock`、`device_count`、`character_count`、
`proactive_enabled`、`timezone`。

---

# v0.3 新增接口（媒体与语音）

## 媒体

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/media` | multipart 上传（`file` + `kind` + `duration_ms`），返回媒体元信息 |
| GET | `/media?kind=&limit=` | 媒体列表 |
| GET | `/media/{id}` | 原始字节（鉴权 + `nosniff`） |
| DELETE | `/media/{id}` | 删除记录；无人引用时才删磁盘文件 |
| POST | `/media/{id}/transcribe` | 语音转写，返回 `{text, mock, language}` |

上传约束：只接受 JPEG/PNG/GIF/WebP/HEIC 与 WAV/M4A/MP3/OGG/AMR，
**按 magic bytes 判断**（客户端声明的 Content-Type 不作数）；图片 8 MiB、语音 20 MiB 上限。

## 语音

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/speech/tts` | `{text, voice?}` → 音频字节；响应头 `X-LUMI-Mock` 标明是否 Mock |
| POST | `/speech/transcribe` | 直接上传音频转写（不落库） |
| GET | `/speech/status` | 是否已接入 ASR / TTS |

未配置 `LUMI_ASR_MODEL` / `LUMI_TTS_MODEL` 时一律走 Mock：
ASR 返回带「未接入」字样的占位文本，TTS 返回静音 WAV——**不会假装识别成功**。

## 聊天携带媒体

```json
POST /api/v1/chat
{"message": "", "media_id": "a7cf...", "kind": "image"}
```

- `kind` ∈ `text | image | audio`；
- `message` 可为空：`audio` 时由服务端转写补全正文，`image` 时补一句
  「（用户发来一张图片）」（没有视觉模型时不假装能看图）；
- 消息落库带 `kind` 与 `media_id`，跨设备同步时另一端按同样方式渲染。
