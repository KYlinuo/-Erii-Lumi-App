# 夜间开发进度日志

> 分支：`night/v0.2`（基线 `master` @ `eeee84f`）
> 环境：Windows 11 / Git Bash / Python 3.13.14（项目 `.venv`）/ pytest 9.1.1
> 原则：每一步都记录**实际执行结果**，不记录任何未执行的"计划完成"。

---

## 23:05 – 23:20 · 审计与基线保护

- 定位工程：`D:/ProjectLUMI`（Git 仓库，3 次提交，工作区干净）；
  桌宠在 `D:/绘梨衣`（仅发布包）。
- 读取全部交付文档（PRD / ARCHITECTURE / API / TEST_REPORT / CHANGELOG / HANDOFF）
  与两条 CI workflow，确认 v0.1 真实能力边界。
- 备份运行期数据库 → `.night-backup/lumi.db.20261027-230719.bak`。
- 建立分支 `night/v0.2`。
- **实测**：`.venv/Scripts/python.exe -m pytest -q` → **54 passed**（v0.1 基线复现成功）。

## 23:20 – 00:10 · 数据层：迁移 + 10 张表

- 新增 `backend/app/migrations.py`：版本化迁移，记录在 `schema_migrations` 表，
  每个步骤幂等（列存在则跳过）。
- 重写 `backend/app/models.py`：
  `User / Device / DeviceCursor / Character / Conversation / Message /
   MemoryRecord / WorldEvent / MediaAsset / ProactiveMessage`。
- `Message` 新增 `request_id`（幂等）、`conv_seq`（同步游标）、
  `client_ts`、`media_id`、`tokens_prompt/completion`、`deleted_at`（tombstone）。
- **实测**：对**真实 v0.1 库副本**执行迁移 → 新表/新列全部就位，
  3 条历史消息原封不动；连续执行 3 次迁移，第二、三次返回空列表（幂等）。
- 回归：54/54 仍通过。

## 00:10 – 00:40 · 身份、模型网关、人格、记忆

- `identity.py`：设备注册、SHA-256 加盐令牌、作用域、吊销。
- `llm/mock.py` + `llm/retry.py`：Mock Provider（model 名固定为 `mock-provider-v1`）、
  只对超时/断连/限流退避重试，Key 无效与坏响应不重试。
- `personas.py`：5 套人格（LUMI / 林穗 / 祁鹿 / 沈昼 / 绘梨衣）。
  绘梨衣的 168 句待机台词从桌宠素材自动抽取 → `resources/erii_whispers.json`。
  **未找到三套人格的原始设计文档**，故 `source="reconstructed"` 并在 UI 标注"设定待补充"。
- `memory.py`：六分类、来源、可信度；`subject` 三级隔离
  （`user` 跨人格共享 / `relationship` 按人格隔离 / `character` 角色虚构）。

## 00:40 – 01:10 · 服务编排与路由

- `services.py`：幂等 → 人格解析 → 用户消息先 commit → 记忆吸收 →
  组装（人格 + 虚构世界 + 记忆 + 历史）→ 带重试调用 → 落库回复。
- 新增路由：`devices / characters / memory / world / sync / proactive`。
- `bootstrap.py`：启动播种人格 + 虚构生活（确定性，不花额度）。

## 01:10 – 01:35 · 测试套件（发现并修复 5 个真实缺陷）

| # | 缺陷（均为测试发现，非事后粉饰） | 修复 |
|---|---|---|
| 1 | 幂等重发在"首次请求上游失败"时直接 `UNIQUE(request_id)` 崩溃（500） | 复用已落库的用户消息重试，不再插入第二条；跨会话冲突返回 409 |
| 2 | SQLite 丢 tzinfo，`created_at` 序列化后没有 `+00:00`，客户端无法判时区 | 新增 `UTCDateTime` 类型装饰器，强制 UTC 存取 |
| 3 | 真实启动 uvicorn 报 `no such table: users`——lifespan 只做了播种没建表 | lifespan 先 `create_all()`（含迁移）再 `bootstrap()` |
| 4 | `bootstrap` 用 `created_at == updated_at` 判断是否新建，两个 default 微秒级不同导致统计恒为 0 | 改为显式查重统计 |
| 5 | ChatMessage 是值类型，`first(where:)` 后原地修改不会写回数组（Swift） | 改为按下标修改数组元素 |

另修正两处质量问题：虚构世界记忆被误标为"推测"；虚构日记出现重复句子
（改为"当天严格幂等 + 7 天窗口内避免复述"）。

- **实测**：`pytest -q` → **144 passed**。

## 01:35 – 02:10 · iOS 客户端 v0.2

- 新增 `Models/PersonaModels.swift`（人格 / 记忆 / 虚构事件 / 同步 / 设备 / 主动联系）。
- 扩展 `ServerModels.swift`（`ChatRequest` 幂等字段、`ChatResponse` 新字段、
  `HealthResponse` v0.2 字段、**并保留对 v0.1 后端的向后兼容**）。
- `LUMIAPIClient` 新增 15 个端点方法，补齐 PATCH / DELETE。
- 新增 `PersonaViewModel / MemoryViewModel / DiaryViewModel`。
- 新增 `ProfileView / MemoryView / DiaryView` + 统一设计规范 `LUMIStyle.swift`。
- `RootView` 改为 `TabView`（聊天 / 人物 / 记忆 / 日记 / 设置）。
- `ChatViewModel`：幂等重发、增量同步、主动消息补拉。
- 新增 `LUMITests/PersonaDecodingTests.swift`（11 项解码测试）。
- **未完成**：Windows 无 Swift 工具链，代码**未经编译器验证**（见交付报告）。

## 02:10 – 02:40 · Windows 整合与真实启动验证

- 交付 `windows-bridge/lumi_bridge.py`（纯标准库）。
- **实测**：启动真后端（uvicorn，Mock Provider）→ 桥接客户端跑通
  `status / register / characters / send / memory / diary`，
  证实 Windows 与 iPhone 可共用同一角色、会话、记忆与虚构时间线。

## 02:40 – 03:00 · 文档与提交

- 编写 `EXISTING_PROJECT_AUDIT.md`、`NIGHT_TASK_QUEUE.md`、本文件、
  `ERII_INTEGRATION.md`、`NIGHT_REPORT.md`、`NEXT_MORNING.md`。
- 更新 `API.md`、`CHANGELOG.md`、`TEST_REPORT.md`、`ARCHITECTURE.md`、`README.md`。
- Git 提交到 `night/v0.2`。
