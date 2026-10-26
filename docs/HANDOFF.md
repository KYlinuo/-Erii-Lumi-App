# Project LUMI v0.1 — 交付交接文档（HANDOFF）

> 生成时间：2026-10-27 · 本文档记录 v0.1 交付基线，供独立审查者（人或 AI）快速接入。
> 所有结论均来自**真实执行结果**，未执行项如实标注。

## 1. Git Commit ID

| 提交 | 哈希 | 日期 | 内容 |
|------|------|------|------|
| 代码基线（后端） | `f388764ed96b82e94d3f5565c19afd89e4d68af0` | 2026-10-26 23:53 +0800 | FastAPI + SQLite + OpenAI 兼容适配器 + 全部后端测试 |
| 代码基线（客户端/CI/文档） | `db60bf6a51bfc75061c9e1b396c7db81aada7db2` | 2026-10-27 00:11 +0800 | SwiftUI iOS 客户端 + GitHub Actions + 全部技术文档 |
| 交付文档 | 本文件所在提交（HANDOFF 新增） | 2026-10-27 | v0.1 交付与审查准备 |

说明：审查压缩包由 `git archive` 从交付提交（HEAD）生成，内容与上述基线一致
（仅新增本文件）。仓库 `.git` 目录不随包分发。

## 2. 交付文件清单（实际创建的源文件）

### 后端（Python / FastAPI，backend/app）
- 入口与配置：`main.py`、`config.py`、`database.py`、`__init__.py`
- 数据模型：`models.py`（Conversation/Message，级联删除）、`schemas.py`
- 业务与安全：`services.py`、`security.py`、`ratelimit.py`
- LLM 适配层：`llm/base.py`、`llm/errors.py`、`llm/factory.py`、`llm/openai_compat.py`
- 路由：`routers/health.py`（health/persona/time）、`routers/chat.py`、`routers/conversations.py`
- 部署配置：`backend/deploy/lumi.service`（systemd）、`backend/deploy/nginx-lumi.conf`
- 依赖：`backend/requirements.txt`、`backend/requirements-dev.txt`

### iOS 客户端（Swift 6 / SwiftUI，frontend/LUMI）
- App 层（3）：`LUMIApp.swift`、`AppSession.swift`、`RootView.swift`
- Models（3）：`ChatMessage.swift`、`ServerModels.swift`、`LUMIError.swift`
- Services（4）：`LUMIAPIClient.swift`、`KeychainStore.swift`、`MessageStore.swift`、`ServerConfiguration.swift`
- ViewModels（2）：`ChatViewModel.swift`、`SettingsViewModel.swift`
- Views（6）：`ChatView.swift`、`MessageBubble.swift`、`ComposerBar.swift`、`SettingsView.swift`、`LUMIAvatar.swift`、`LaunchView.swift`
- 工程与资源：`project.yml`（XcodeGen）、`Info.plist`、`Assets.xcassets`（含 1024×1024 App Icon）

### 测试
- 后端 pytest（6 个文件，54 个用例）：`tests/test_health.py`、`test_chat.py`、`test_conversations.py`、`test_auth.py`、`test_provider_adapter.py`、`test_ratelimit.py` + `conftest.py`
- iOS XCTest（3 个文件）：`frontend/LUMITests/ChatMessageTests.swift`、`DecodingTests.swift`、`ErrorMappingTests.swift`

### GitHub Actions（2 个工作流）
- `.github/workflows/backend-tests.yml`：Ubuntu + Python 3.12 跑 pytest + 环境自检
- `.github/workflows/ios-build.yml`：macos-15，XcodeGen → 模拟器单测 → 模拟器构建 → 未签名 IPA → 产物上传

### 脚本与文档
- `scripts/check_env.py`、`gen_token.py`、`run_backend.py`、`smoke_test.py`、`gen_assets.py`
- `README.md`、`docs/PRD.md`、`docs/ARCHITECTURE.md`、`docs/API.md`、`docs/CHANGELOG.md`、`docs/TEST_REPORT.md`、`docs/HANDOFF.md`（本文件）

## 3. 构建与测试结果（真实执行，2026-10-26/27）

| 项目 | 结果 | 说明 |
|------|------|------|
| 后端单元测试 | ✅ **54/54 通过** | `python -m pytest tests/ -v`，pytest 9.1.1，Python 3.13 |
| 端到端冒烟（真实启动 uvicorn） | ✅ **4/4 通过** | health=ok/database=ok、persona=LUMI、conversations 鉴权 200；真实模型调用项在本机未配置 Key，故跳过 |
| iOS 编译 / XCTest | ⚠️ **未在本机验证** | Windows 无 Swift/iOS SDK，无法执行 `xcodebuild`；源码与 CI 工作流已就绪，需 macOS 或 GitHub Actions 验证 |
| GitHub Actions 运行 | ⚠️ 未执行 | 仓库未推送到远端，workflow 尚未被触发 |

## 4. AI API 调用与聊天历史持久化（如实核查）

- **AI API 调用已实际接线**：`llm/openai_compat.py` 通过 httpx 真实 POST 到
  `{base_url}/v1/chat/completions`（默认 DeepSeek），携带 `Authorization: Bearer <key>`。
  `services.send_message` 编排：未配置 `LUMI_API_KEY` 时返回 `503 provider_not_configured`，
  **不存在任何伪造回复路径**（有测试覆盖）。
- **本环境未做过真实模型调用**：本机 `.env` 未配置真实 API Key（符合安全约定，不入库不入包）。
  单元测试使用桩适配器 + httpx MockTransport 模拟协议（12 项），真实网络行为验证需配置 Key 后
  执行 `python scripts/smoke_test.py --real-model`。
- **聊天历史已持久化**：SQLAlchemy + SQLite（`backend/data/lumi.db`，WAL 模式）。
  用户消息先 commit 再调模型（上游失败不丢）；回复落库含 model/latency；
  级联删除、跨连接会话恢复均有测试覆盖（`test_chat_persists_both_sides`、
  `test_history_survives_new_engine_session` 等）。运行期数据库**不含**在审查包内。

## 5. 客户端 ↔ 后端数据格式一致性（已逐字段核对）

- `POST /api/v1/chat`：请求 `message` / `conversation_id`（snake_case）↔ 客户端 `ChatRequest`
  CodingKeys 显式映射；响应 6 字段（`conversation_id`、`user_message_id`、`assistant_message_id`、
  `reply`、`model`、`latency_ms`）↔ `ChatResponse` 逐一对齐。
- `GET /health`、`/persona`、`/conversations`、`/conversations/{id}/messages` 的字段与
  `ServerModels.swift` / `LUMITests/DecodingTests.swift` 一致。
- 错误信封统一 `{"error": {"code","message","hint"}}` + `X-LUMI-Error-Code` 头，
  客户端 `ErrorEnvelope` 解析一致；限流 `Retry-After` 已在客户端处理。
- 认证：客户端发 `X-LUMI-TOKEN` 头，后端兼容 `X-LUMI-TOKEN` 与 `Bearer`（测试覆盖两种）。
- 客户端不发送 `history` 字段（后端从 SQLite 读取上下文），schema 中该字段为可选，兼容无冲突。

## 6. 未解决问题与已知限制

1. **iOS 编译未经真实工具链验证**（Windows 无法本地执行）——当前唯一未闭环项；
   验证路径：GitHub Actions（push 触发）或任意 macOS 执行 `xcodegen generate && xcodebuild test`。
2. 仓库尚未推送到 GitHub，两条 CI 工作流未实际运行过。
3. 限流为单进程内存实现，多实例部署需换 Redis。
4. 回复为非流式（v0.2 计划 SSE）。
5. 真实模型端到端调用（产生 API 费用的那一步）待配置 Key 后验证。

## 7. 审查包说明

- 包名：`ProjectLUMI-v0.1-review.zip`（生成于项目目录之外，即 D 盘根目录旁路）。
- 生成方式：`git archive`（只含 Git 跟踪文件），自动排除以下内容：
  - `.git/` 历史目录
  - `.venv/`、`__pycache__/`、`.pytest_cache/` 等依赖与缓存
  - `backend/data/`（含聊天记录的运行期数据库）
  - `.env` 及一切密钥/证书文件（`*.pem`/`*.key` 等，从未入库）
  - 运行日志
- 包内 `.env.example` 仅含变量名占位符，无真实凭据。
- 审查入口建议：`README.md` → `docs/ARCHITECTURE.md` → `docs/API.md` → `docs/TEST_REPORT.md` →
  后端跑 `pip install -r backend/requirements-dev.txt && python -m pytest -q` 即可复现 54 项测试。

## 8. 交付状态

v0.1 交付基线冻结。除本 HANDOFF 文档外不再修改代码，等待独立代码审查。
