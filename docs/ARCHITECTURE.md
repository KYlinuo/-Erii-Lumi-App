# Project LUMI — 架构文档 v0.1

## 1. 总览

```
┌─────────────────────────┐          HTTPS/HTTP           ┌──────────────────────────┐
│  iOS 客户端 (Swift 6)    │  ──────────────────────────▶  │  后端 (Python/FastAPI)    │
│                         │   X-LUMI-TOKEN 认证            │                          │
│  SwiftUI + NavigationStack                             │  ┌────────────────────┐  │
│  URLSession async       │  ◀──────────────────────────  │  │ OpenAI 兼容适配器    │──┼──▶ DeepSeek
│  Keychain(令牌)          │        JSON                   │  │ (deepseek 等)       │  │    /任意兼容网关
│  本地 JSON 持久化        │                               │  └────────────────────┘  │
└─────────────────────────┘                               │  SQLite(SQLAlchemy)      │
                                                          └──────────────────────────┘
```

## 2. 后端结构（backend/app）

| 模块 | 职责 |
|------|------|
| `config.py` | 全部配置来自环境变量（pydantic-settings），`.env` 不入库 |
| `database.py` | SQLAlchemy 引擎/会话；SQLite WAL + 外键；测试可用内存库 |
| `models.py` | `Conversation` / `Message`，删除会话级联删除消息 |
| `schemas.py` | Pydantic 请求/响应模型（snake_case 字段对齐客户端） |
| `security.py` | 单用户认证：`X-LUMI-TOKEN` 或 `Bearer`；hmac.compare_digest 防时序攻击；生产环境强制 token，否则拒绝启动 |
| `ratelimit.py` | 内存滑动窗口限流，`chat` 与 `default` 两个作用域独立计数 |
| `llm/openai_compat.py` | OpenAI 兼容 `/chat/completions` 适配器（DeepSeek、vLLM、Ollama 等通用） |
| `llm/errors.py` | 上游错误 → 7 种细分错误码 + HTTP 状态映射 |
| `services.py` | 业务编排：落库用户消息 → 组装上下文（system+40 条历史）→ 调模型 → 落库回复 |
| `routers/` | `health`（状态/persona）、`chat`（发消息）、`conversations`（历史管理） |

### 关键设计决策

1. **用户消息先 commit 再调模型**：上游超时/断网时，用户说的话已经保存，
   App 重启后历史完整。
2. **绝不伪造回复**：未配置 `LUMI_API_KEY` 时返回 `503 provider_not_configured`，
   而不是返回占位文本冒充模型输出。
3. **统一错误信封** `{"error": {"code","message","hint"}}`：认证、限流、上游错误
   全部同构，客户端只解析一种结构（`X-LUMI-Error-Code` 头便于日志排查）。
4. **上下文窗口**：取最近 40 条成功消息作为历史，排除刚落库的当前消息避免重复。

## 3. iOS 客户端结构（frontend/LUMI）

```
LUMI/
├── App/          LUMIApp(App 入口) · AppSession(启动编排) · RootView(NavigationStack)
├── Models/       ChatMessage(本地消息) · ServerModels(传输模型) · LUMIError(错误语义)
├── Services/     LUMIAPIClient(URLSession) · KeychainStore(令牌) · MessageStore(本地持久化) · ServerConfiguration
├── ViewModels/   ChatViewModel(聊天编排) · SettingsViewModel(连接状态)
└── Views/        LaunchView · ChatView · MessageBubble · ComposerBar · SettingsView · LUMIAvatar(矢量形象)
```

- **形象独立**：`LUMIAvatar` 用 SwiftUI 矢量绘制（发色/瞳色/腮红/呆毛），任意尺寸清晰；
  App Icon 由 `scripts/gen_assets.py` 以同一套配色程序化生成。
- **密钥边界**：客户端只持有「服务器地址 + 访问令牌」；令牌入 Keychain
  （`AfterFirstUnlockThisDeviceOnly`，不随备份迁移）。模型 Key 永不出现在客户端代码/配置。
- **本地持久化**：`MessageStore` actor 把消息快照写 JSON（原子写），冷启动先读本地，
  再按需从服务端补齐；文件损坏时自动隔离，不让 App 崩溃。
- **Swift 6 严格并发**：`LUMIAPIClient` 为 `Sendable`，ViewModel 全部 `@MainActor`，
  持久化用 actor，开启 `SWIFT_STRICT_CONCURRENCY=complete`。

## 4. 构建

- 工程唯一事实来源是 `frontend/project.yml`（纯文本，Windows 可维护）；
  macOS/CI 执行 `xcodegen generate` 生成 `LUMI.xcodeproj`。
- CI（`.github/workflows/ios-build.yml`，macOS-15 runner）：
  1. XcodeGen 生成工程 →
  2. iPhone 模拟器跑 `LUMITests` →
  3. 构建模拟器 App 产物 →
  4. `CODE_SIGNING_ALLOWED=NO` 归档真机版本并打包**未签名 IPA**（供 AltStore/Sideloadly 侧载）。
- 后端 CI（`backend-tests.yml`）在 Ubuntu 上跑 pytest。

## 5. 部署（backend/deploy）

- `nginx-lumi.conf`：TLS 终结（Let's Encrypt）→ 127.0.0.1:8000，带 HSTS 等安全头；
- `lumi.service`：systemd 单元，`LUMI_ENV=prod`，最小权限（ProtectSystem=strict）。
- 后端只监听回环地址，不直接暴露公网。

## 6. 已知限制（v0.1）

- 限流为单进程内存实现，多实例部署需换 Redis；
- 消息为非流式返回（v0.2 计划 SSE）；
- iOS 构建目前只能由 macOS/CI 执行，Windows 上无法本地编译验证。
