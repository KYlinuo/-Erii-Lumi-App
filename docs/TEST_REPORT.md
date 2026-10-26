# Project LUMI v0.1 — 测试报告

> 生成时间：2026-10-26 · 报告基于**真实执行结果**，未执行的项目如实标注为「未验证」。

## 1. 执行环境

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
