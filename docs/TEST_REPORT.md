# Project LUMI — 测试报告

> 最新更新：2026-10-29 晚间 · 报告基于**真实执行结果**，未执行项如实标注。
> 历史版本（v0.1/v0.3）记录保留在文末，供追溯。

## 0. 当前基线（2026-10-29 阶段 A）

| 项 | 值 |
|----|----|
| 后端 pytest | **199 项全绿**（`199 passed`，本机 Windows） |
| iOS 构建 | 上一轮 `69cba89` GitHub Actions 编译全绿（38 项 XCTest）；阶段 A 仅后端改动，未触发 iOS 构建 |
| 数据备份 | `backend/data/backups/lumi-20261029-211915.db`（SQLite backup API，integrity 通过） |
| 生产库角色归档 | 已验证：4 旧角色 `is_active=0`、绘梨衣 `is_default=1`、`/characters` 只返回绘梨衣 |

### 阶段 A 新增测试

| 文件 | 项数 | 覆盖 |
|---|---|---|
| `tests/test_character_archive.py` | 3 | 旧库角色归档、幂等、历史会话数据不丢 |
| `tests/test_message_reliability.py` | 3 | 连发顺序、幂等重放不重复、重试幂等 |

### 未执行项（如实标注）

- **iOS 编译**：阶段 A 未改 Swift，未触发 iOS 构建；下一阶段（阶段 B）改前端后补。
- **真机验收**：无 macOS/Xcode 本机环境，视觉/壁纸/键盘等需真机检查项待装包验证。

---

## 1. 历史执行环境（v0.1）

| 项 | 值 |
|----|----|
| 操作系统 | Windows（Git Bash / win32） |
| Python | 3.13.14（项目 venv：`.venv`） |
| pytest | 9.1.1（pytest-asyncio 1.4.1） |
| Git | 2.55.0.windows.3 |
| 后端实测 | uvicorn 127.0.0.1:8000，SQLite `backend/data/lumi.db` |
| Swift 工具链 | **本机无**（Windows 无 iOS SDK，iOS 编译未在本机执行） |

## 2. 后端单元测试（pytest）— ✅ 54/54 通过

```
============================= 54 passed in 2.54s ==============================
```

| 测试文件 | 数量 | 覆盖内容 |
|---------|-----|---------|
| `tests/test_health.py` | 5 | 健康检查、provider 状态联动、**密钥不泄露**、persona、根端点 |
| `tests/test_chat.py` | 8 | 真实适配器调用、系统提示词与历史组装、双端落库、空消息/超长拒绝、未配置 Key→503、**5 类上游失败映射**、上游失败仍保存用户消息 |
| `tests/test_conversations.py` | 7 | 历史按序恢复、跨数据库会话持久化、会话计数、标题生成与截断、级联删除、未知会话、孤儿消息清理 |
| `tests/test_auth.py` | 9 | 公开端点放行、缺 token/错 token 拒绝、Bearer 兼容、常量时间比较、dev 放行、**生产无 token 拒绝启动**、health 上报认证状态 |
| `tests/test_provider_adapter.py` | 12 | OpenAI 兼容协议、URL 拼接（含 /v1）、未配置检测、6 组 HTTP 状态映射、超时、连接失败、坏响应、空内容、错误体截断、**错误信息不泄露 API Key** |
| `tests/test_ratelimit.py` | 8 | chat/default 独立配额、429 响应结构与 Retry-After、窗口滑动、滑动窗口单元、0 限流禁用、配置默认值 |

测试策略：单元测试注入桩适配器（`StubProvider`），**永不调用真实 DeepSeek API**；
真实网络行为由 `tests/test_provider_adapter.py` 用 httpx MockTransport 模拟。

## 3. 端到端冒烟测试（真实运行的后端）— ✅ 4/4 通过

`python scripts/smoke_test.py --base-url http://127.0.0.1:8000`

```
[PASS] GET /api/v1/health — status=ok, database=ok, version=0.1.0
[PASS] database == ok — ok
[PASS] GET /api/v1/persona — LUMI
[PASS] GET /conversations 鉴权 — status=200
```

`--real-model` 场景：后端未配置 `LUMI_API_KEY` 时，`POST /chat` 返回
`503 provider_not_configured` —— 这是**符合设计的真实状态**（绝不返回伪造回复），
配置真实 Key 后该检查项会真实调用 DeepSeek。

环境自检 `scripts/check_env.py`：7 项 OK / 1 项 WARN（`.env` 未创建，属预期）/
1 项 SKIP（无 xcodebuild）。

## 4. 开发过程中发现并修复的真实缺陷

| # | 缺陷 | 修复 |
|---|------|------|
| 1 | `Depends(rate_limit(...))` 双重包装导致 `AssertionError: A parameter-less dependency must have a callable dependency`，应用无法启动 | `rate_limit()` 直接返回依赖对象，路由处不再重复包裹 |
| 2 | **用户消息被拼进上下文两次**（先落库又被历史读回），模型会收到重复输入 | `_build_context` 增加 `exclude_message_id` 排除刚写入的消息 |
| 3 | 认证失败/限流返回 `{"detail": …}`，与业务错误信封 `{"error": …}` 不一致 | 增加 `HTTPException` 全局处理器，统一为 `{"error": {code,message,hint}}` |
| 4 | 冒烟脚本被本机 `HTTP_PROXY` 劫持，访问 127.0.0.1 报 `upstream connect failed (os error 10061)` | 使用空 ProxyHandler 的 opener 绕过代理 |
| 5 | 内存 SQLite 每连接独立空库，测试互相看不到数据 | `StaticPool` + `check_same_thread=False` |

## 5. iOS 客户端 — ⚠️ 源码完成，编译未在本机验证

**如实说明**：Windows 上没有 Swift/iOS SDK，本报告**没有**执行过 `xcodebuild`，
因此不声称「iOS 构建已通过」。已交付并可直接验证的内容：

- 19 个 Swift 源文件（App/Models/Services/ViewModels/Views）+ 4 个 XCTest 测试文件，
  代码按 Swift 6 严格并发编写（`Sendable`、`@MainActor`、actor）；
- `frontend/project.yml`（XcodeGen）+ `Info.plist` + Asset Catalog（含程序化生成的
  1024×1024 App Icon PNG，已人工目检渲染结果正确）；
- CI 工作流 `.github/workflows/ios-build.yml`（macos-15）：模拟器单测 → 模拟器构建 →
  真机未签名 IPA → 产物上传；构建失败会以非零退出码结束并上传日志。

**验证方式**：推送到 GitHub 触发 workflow，或任意 macOS 上
`brew install xcodegen && cd frontend && xcodegen generate && xcodebuild test`。

## 6. 验收标准核对（PRD v0.1 十项）

| # | 需求 | 证据 |
|---|------|------|
| 1 | 原生启动界面 | `LaunchView.swift`（形象动画 + 探测状态） |
| 2 | 独立头像与名称 | `LUMIAvatar.swift` 矢量形象 + 程序化 App Icon + `GET /persona` |
| 3 | 原生聊天 UI | `ChatView` / `MessageBubble` / `ComposerBar` / `TypingIndicator` |
| 4 | 发送文字消息 | `ChatViewModel.send`，空消息禁发、8000 字上限（422 测试覆盖） |
| 5 | 后端调用真实模型 | `OpenAICompatibleProvider` → DeepSeek；MockTransport 12 项协议测试 |
| 6 | 消息保存 SQLite | `Message` 模型 + `test_chat_persists_both_sides` |
| 7 | 重启恢复历史 | `test_history_is_restored_in_order` / `test_history_survives_new_engine_session` + 客户端 `MessageStore` 快照 |
| 8 | 失败/断网/超时提示 | 7 错误码映射测试 + 客户端 `LUMIError.userMessage` 映射测试 |
| 9 | 设置页连接状态 | `SettingsView` + `/health`（版本/模型/数据库/认证/密钥指纹） |
| 10 | 真实 API 端点 | `test_chat_when_api_key_missing`：未配置即 503，无任何假回复路径 |

## 7. 结论

- 后端：**54/54 单元测试通过**，真实服务端到端冒烟 4/4 通过，可作为 v0.1 基线。
- iOS：源码与工程配置完备，**编译验证待 macOS/CI 执行**，这是当前唯一未闭环项。

---

# v0.2 测试报告（2026-10-28 · 夜间开发）

> 全部结论来自**真实执行**。未执行的项目一律标注为「未验证」。

## 1. 执行环境

| 项 | 值 |
|----|----|
| 操作系统 | Windows 11（Git Bash / win32） |
| Python | 3.13.14（项目 `.venv`） |
| pytest | 9.1.1 |
| 后端实测 | uvicorn 127.0.0.1 + SQLite |
| Swift 工具链 | **本机无**（iOS 编译 / XCTest 未在本机执行） |

## 2. 后端单元测试 — ✅ 144/144 通过

```
144 passed in 22.63s
```

| 测试文件 | 数量 | 覆盖内容 |
|---------|-----|---------|
| `test_auth.py` | 10 | 公开端点放行、缺/错 token 拒绝、Bearer 兼容、常量时间比较、生产无 token 拒绝启动 |
| `test_chat.py` | 8 | 真实适配器调用、历史组装、双端落库、未配置 Key→503、5 类上游失败映射、失败仍保存用户消息 |
| `test_conversations.py` | 8 | 历史按序恢复、跨会话持久化、标题生成与截断、级联删除、孤儿消息清理 |
| `test_devices.py` | 8 | 注册返回一次性明文令牌、库内只存哈希、令牌可认证、吊销即失效、作用域收窄、改名、404 |
| `test_health.py` | 5 | 健康检查、provider 状态、**密钥不泄露**、persona、根端点 |
| `test_llm_gateway.py` | 16 | Mock Provider 确定性与脚本化、**不会悄悄顶替真实模型**、3 类可重试/3 类不可重试、退避递增、Token 记账落库、人格与记忆注入上下文、切人格不合并 |
| `test_memory.py` | 16 | 抽取确定性、可关闭、用户事实跨人格共享、关系记忆按人格隔离、虚构人生不泄漏到用户事实、幂等不重复、来源与可信度、归档/删除/导出、接口往返 |
| `test_migrations.py` | 4 | **v0.1 老库原地升级**（数据保全 + 游标回填 + 索引建立）、重复执行幂等、迁移后 ORM 可读写新字段 |
| `test_personas.py` | 12 | 5 套人格齐备、唯一默认人格、**播种不覆盖既有设定**、人格不合并、未知 key 回退、提示词含虚构声明、虚构人生按人格隔离、待机台词 |
| `test_proactive.py` | 12 | 默认关闭、免打扰时段、非允许时段、允许时段、**每日配额**、离线排队、投递标记、一键取消、接口不声称 APNs |
| `test_provider_adapter.py` | 15 | OpenAI 兼容协议、URL 拼接、6 组 HTTP 状态映射、超时、连接失败、错误信息不泄露 Key |
| `test_ratelimit.py` | 8 | chat/default 独立配额、429 与 Retry-After、窗口滑动、0 限流禁用 |
| `test_sync.py` | 9 | **两台设备（iPhone + Windows）共享会话**、增量只返回新增、`conv_seq` 单调、幂等重发不重复、不同 request_id 正常分开、游标读写、tombstone 同步、UTC 时间、人格一致 |
| `test_world.py` | 13 | 生成事件、同一天幂等、确定性、时间线排序与过滤、`since` 生效、非法 kind 拒绝、日记接口标注虚构、日期参数与 422 |

测试策略：单元测试注入桩适配器，**永不调用真实模型 API**（不产生费用）；
真实网络协议由 `httpx.MockTransport` 模拟。

## 3. 端到端验证（真实运行的后端）— ✅ 通过

- **uvicorn 真实启动**：`LUMI v0.2.0 starting` → `bootstrap done:
  {characters_created: 5, fictional_memories: 10, world_events: 20}` →
  `Uvicorn running on http://127.0.0.1:8013`。
- **Windows 桥接客户端实机跑通**：`status` → `register` → `characters` →
  `send` → `memory` → `diary` 全部成功，证实 Windows 与 iPhone 共用同一角色、
  会话、消息、记忆与虚构时间线。
- **`/api/v1/health` 实测返回**：
  `status=ok, database=ok, schema_version=2026102702, is_mock=true,
  character_count=5`。

## 4. 本次新增测试发现的真实缺陷（均已修复）

| # | 缺陷 | 修复 |
|---|------|------|
| 1 | 幂等重发在「首次请求上游失败」时触发 `UNIQUE(request_id)`，请求直接 500 | 复用已落库的用户消息重试；`request_id` 属于其它会话时返回 409 |
| 2 | SQLite 丢 tzinfo，`created_at` 序列化后没有 `+00:00` | 新增 `UTCDateTime` 类型装饰器，强制 UTC 存取 |
| 3 | 真实启动报 `no such table: users`（lifespan 只播种未建表） | lifespan 先 `create_all()`（含迁移）再 `bootstrap()` |
| 4 | `bootstrap` 用 `created_at == updated_at` 判新建，恒为 0 | 改为显式查重统计 |
| 5 | Swift `ChatMessage` 值类型原地修改丢失 | 改为按下标写回数组 |
| 6 | 虚构世界记忆被误标为「推测」 | 拆分为 `isInferred`（推断）/ `isSimulated`（角色设定） |
| 7 | 虚构日记出现重复句子 | 当天严格幂等 + 7 天窗口内避免复述 |

## 5. iOS 客户端 — ⚠️ 源码完成，编译未在本机验证

与 v0.1 相同：**Windows 上没有 Swift / iOS SDK**，本报告**没有**执行过
`xcodebuild`，因此不声称「iOS 构建已通过」。已交付：

- 新增 3 个页面（人物 / 记忆 / 虚构日记）+ 设计规范 + 3 个 ViewModel +
  传输模型 + 15 个 API 方法；
- 新增 `LUMITests/PersonaDecodingTests.swift`（11 项解码测试，含 v0.1 后端兼容）；
- `project.yml` 版本号升至 0.2.0，两条 workflow 增加 `night/**` 触发。

验证方式：推送到 GitHub 触发 Actions，或任意 macOS 上
`brew install xcodegen && cd frontend && xcodegen generate && xcodebuild test`。

## 6. 未验证项（如实列出）

1. iOS 编译与 XCTest；
2. GitHub Actions 实际运行（仓库尚未推送到远端）；
3. 真实模型端到端调用（本机无 `LUMI_API_KEY`，本次**未产生任何 API 费用**）；
4. 真机安装与 APNs（免费自签不支持远程推送）。

---

# v0.3 测试报告（2026-10-28 · 第二阶段）

## 1. 后端 — ✅ 164/164 通过

```
164 passed in 35.31s
```

新增 `tests/test_media.py`（15 项）：

| 用例 | 验证的行为 |
|---|---|
| `test_upload_image_and_download` | 上传→下载字节完全一致，响应带 `nosniff` |
| `test_rejects_fake_mime` | 把 HTML 声明成 `image/png` 必须被 magic bytes 拦下 |
| `test_upload_is_authenticated` | 无令牌 401 |
| `test_client_filename_is_ignored` | 客户端传 `../../../../evil.png` 也只是普通文件名 |
| `test_duplicate_content_reuses_storage` | 相同内容复用一条记录，不重复占盘 |
| `test_audio_upload_and_transcribe_mock` | 未接入 ASR 时 `mock=true` 且文本含「未接入」 |
| `test_transcribe_rejects_image` | 图片不能转写，返回 422 `not_audio` |
| `test_tts_returns_playable_wav_marked_mock` | TTS Mock 产出真 WAV（`RIFF` 头 + 有帧） |
| `test_tts_rejects_empty_text` | 空文本 422 |
| `test_speech_status_reports_mock` | 状态接口如实报告 Mock |
| `test_chat_with_image_media` | 图片消息落库 `kind=image` + `media_id` |
| `test_chat_with_audio_media_uses_transcript` | 纯语音消息由转写补全正文 |
| `test_chat_with_unknown_media_returns_404` | 媒体不存在返回 `media_not_found` |
| `test_delete_removes_file_and_record` | 删除同时清掉磁盘文件 |
| `test_media_list_filters_by_kind` | `kind` 过滤生效 |

迁移测试同步更新，覆盖新增的 `2026102801` 步骤。

## 2. 真实服务器端到端 — ✅ 通过

`uvicorn` 实起 127.0.0.1:8031（`LUMI_PROVIDER=mock`）：

1. `POST /media`（70 字节 PNG）→ 201，返回 `storage_uri=c4/<id>.png`；
2. `POST /chat` `{"message":"看看这个","media_id":...,"kind":"image"}` → 200，有回复；
3. `POST /speech/tts` → 200，`x-lumi-mock: true`，57644 字节可播放 WAV；
4. `GET /speech/status` → `{"asr_configured":false,"tts_configured":false,"mock":true}`。

## 3. iOS — ⚠️ 语法级验证通过，编译仍未执行

新增 `scripts/swift_lint.py`（tree-sitter 语法解析 + 括号配平 + 顶层重复声明）：

```
swift files: 33
declared types: 87
未发现阻断问题
```

这是**语法级**证据，不等于编译通过。类型检查、SwiftUI 视图构建、Swift 6 严格并发
仍然只能在 macOS 上验证。本机没有 Swift 工具链，因此本报告不声称 iOS 构建成功。

## 4. 未验证项

1. iOS 编译 / XCTest（含新增的 7 项媒体解码测试）；
2. GitHub Actions 实际运行（推送需要人工授权一次，见 `NEXT_MORNING.md`）；
3. 真实 ASR / TTS（无密钥，零费用）；
4. 真机录音权限弹窗与蓝牙耳机切换（需要设备）。

## 5. 真实旧库原地升级（v0.1 → v0.3）— ✅ 通过

用**仓库里真实存在的** `backend/data/lumi.db` 副本（它连 `schema_migrations` 表都没有，
属于 v0.1 时代的库）直接启动 v0.3 后端：

```
迁移前：messages 列 = [content, status, model, error_code, latency_ms, created_at]
        消息 1 条，无 schema_migrations 表

启动后：/health → {"status":"ok","version":"0.3.0",
                  "schema_version":"2026102801","character_count":5}
迁移后：messages 列补到 [... client_ts, media_id, tokens_*, deleted_at, kind]
        消息仍是 1 条（内容未动），kind 自动落到 'text'
        版本记录 = [2026102701, 2026102702, 2026102801]
```

结论：**没有删库、没有丢消息**，老数据自动补默认值。这是"迁移而不是重建"的直接证据。
