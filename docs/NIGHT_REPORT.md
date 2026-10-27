# Project LUMI — 夜间开发交付报告

> 按要求逐项如实填写。没有做到的地方一律写「未完成」，不做任何粉饰。

---

## 1. 实际运行时间

| 项 | 值 |
|----|----|
| 起始 | 2026-10-27 23:05（北京时间） |
| 结束 | 2026-10-28 03:00（北京时间） |
| 有效开发时长 | 约 3 小时 55 分（持续执行，中途无人工介入、未询问任何问题） |
| 停止新模型调用 | 2026-10-28 03:00 前 |

## 2. 当前工程版本

| 项 | 值 |
|----|----|
| 版本 | **v0.2.0**（`backend/app/__init__.py`、`frontend/project.yml` 均已升版） |
| 分支 | `night/v0.2` |
| 基线 | `master` @ `eeee84f7e3a6a4aa6ad0756da2e1a73e21f20bb2` |
| Git Commit ID | **`74cfa38`（代码） / `7312fff`（文档）** |
| 数据库 schema | `2026102702` |
| 工作区 | 提交后干净（67 个变更文件已入库） |

## 3. 完成的功能

### 后端（统一 AI 后端）
- **版本化数据库迁移**：老库原地升级、记录在 `schema_migrations`、每步幂等，**不删库**
- **数据模型 10 张表**：users / devices / device_cursors / characters / conversations /
  messages / memory_records / world_events / media_assets / proactive_messages
- **身份与设备**：设备注册、每设备独立令牌（服务端只存加盐 SHA-256）、作用域、吊销
- **模型网关**：退避重试（只对超时/断连/限流重试）、Token 消耗记账、
  Mock Provider（`model=mock-provider-v1`，可追查，**不会悄悄顶替真实模型**）
- **人格引擎**：LUMI / 林穗 / 祁鹿 / 沈昼 / 绘梨衣，互不合并，播种只补空字段
- **长期记忆**：六分类 + 来源 + 可信度，`subject` 三级隔离
- **虚构人生**：日记/爱好/阅读/关系/目标时间线，确定性生成（不消耗额度），全部标 `simulated`
- **主动联系**：允许时段、每日上限、最小间隔、夜间免打扰、即时关闭
- **跨设备同步**：`conv_seq` 游标、`request_id` 幂等去重、tombstone、设备游标

### iOS 客户端
- 新增**人物主页**、**记忆页**、**虚构日记页**；`RootView` 改为 TabView 五页导航
- 统一设计规范 `LUMIStyle.swift`（柔和光影 + 玻璃质感 + 深色）
- `ChatViewModel`：幂等重发、增量同步、主动消息补拉
- 传输模型向后兼容 v0.1 后端

### Windows
- `windows-bridge/lumi_bridge.py`：纯标准库桥接客户端，实机跑通全流程

## 4. 修改的文件

共 **67 个变更**（`git status` 实测），其中：

**新增（30）**
`backend/app/`：`migrations.py` `identity.py` `personas.py` `memory.py` `world.py`
`proactive.py` `bootstrap.py` `errors.py` `llm/mock.py` `llm/retry.py`
`routers/{devices,characters,memory,world,sync,proactive}.py` `resources/erii_whispers.json`
`frontend/LUMI/`：`Models/PersonaModels.swift` `ViewModels/{Persona,Memory,Diary}ViewModel.swift`
`Views/{ProfileView,MemoryView,DiaryView,LUMIStyle}.swift`
`frontend/LUMITests/PersonaDecodingTests.swift`
`tests/`：`test_migrations` `test_devices` `test_personas` `test_memory` `test_sync`
`test_world` `test_proactive` `test_llm_gateway`
`windows-bridge/lumi_bridge.py`

**修改（22）**
`backend/app/`：`models.py` `services.py` `security.py` `schemas.py` `database.py`
`config.py` `main.py` `__init__.py` `llm/factory.py`
`routers/{chat,conversations,health}.py`
`frontend/LUMI/`：`App/AppSession.swift` `App/RootView.swift`
`Models/{ChatMessage,ServerModels,LUMIError}.swift`
`Services/LUMIAPIClient.swift` `ViewModels/ChatViewModel.swift`
`frontend/project.yml` `tests/conftest.py`
`.github/workflows/{ios-build,backend-tests}.yml`

**文档**：`EXISTING_PROJECT_AUDIT.md`（新增）、`NIGHT_TASK_QUEUE.md`（新增）、
`NIGHT_PROGRESS.md`（新增）、`ERII_INTEGRATION.md`（新增）、`NEXT_MORNING.md`（新增）、
本报告（新增），以及 `API.md` / `CHANGELOG.md` / `TEST_REPORT.md` 追加 v0.2 章节。

**未触碰**：`D:/绘梨衣` 下任何文件（只读了文档与文本素材）。

## 5. 实际执行的测试

| 项目 | 结果 |
|------|------|
| v0.1 基线回归（改造前） | ✅ **54/54 通过** |
| v0.2 全量测试（改造后） | ✅ **144/144 通过**（22.63s） |
| v0.1 老库原地升级（真实 v0.1 库副本） | ✅ 通过，3 条历史消息原封不动 |
| 真实 uvicorn 启动 | ✅ 通过，`bootstrap done: characters=5, memories=10, events=20` |
| Windows 桥接客户端端到端 | ✅ 通过（status/register/characters/send/memory/diary） |
| 双设备共享会话（iPhone + Windows 两个令牌） | ✅ 通过（9 项） |
| iOS 编译 / XCTest | ❌ **未执行**（Windows 无 Swift/iOS SDK） |

## 6. 成功与失败记录

**成功**：见第 3、5 节。另修复了 7 个由测试发现的真实缺陷（见 `TEST_REPORT.md` 第 4 节），
其中最关键的三个是：
1. 幂等重发在首次请求失败时会 500 —— 已改为复用已落库消息重试；
2. SQLite 丢失时区信息 —— 已加 `UTCDateTime`；
3. 真实启动时 `no such table: users` —— lifespan 补上建表/迁移。

**失败 / 未完成（BLOCKED，已如实记录并继续其他任务）**：

| 项 | 原因 |
|---|---|
| iOS 编译、XCTest、IPA | 本机无 Swift / iOS SDK，无 Mac |
| 真实模型调用 | 本机无 `LUMI_API_KEY`，**本次未产生任何 API 费用** |
| 三套人格原始设计文档 | 磁盘上不存在（见审计报告第 4 节） |
| 66 组语料 / `Project_LUMI_data_schema.json` | 磁盘上不存在 |
| 桌宠进程内集成 | 桌宠为 Electron 发布包，无源码 |
| APNs 远程推送 | 免费自签不支持 |
| 语音 / ASR / TTS / 图片消息 | 时间分配让位于核心链路（`media_assets` 已预留） |

## 7. Git Commit ID

| 提交 | 哈希 | 内容 |
|------|------|------|
| 代码主体 | `74cfa38e0afd77599db66dd8f801ba28f601641a` | v0.2 后端 + iOS + 桥接 + 测试（67 个文件） |
| 交付文档 | `7312fffcb9a60c67022ec3d3df53e28e9b1340b2` | 审计 / 任务队列 / 进度 / 集成方案 / 次日说明 / 本报告 / README |

分支 `night/v0.2`，父提交 `eeee84f`，**未强推、未改写历史、未删除文件**。

## 8. 构建结果

- **后端**：✅ 可构建可运行。`uvicorn app.main:app` 真实启动并通过健康检查。
- **iOS**：❌ **未构建**。Windows 无 iOS SDK。已交付的 `frontend/project.yml`
  + `.github/workflows/ios-build.yml` 可在 macOS / CI 上一键生成工程并构建。
- **GitHub Actions**：⚠️ 配置就绪（两条 workflow 已加 `night/**` 触发），
  但仓库尚未推送到远端，**未实际运行过**。

## 9. IPA 是否已经生成

**否。** 没有生成任何 IPA。原因：本机不具备 iOS 构建条件。
workflow 中已配置「未签名 IPA」产出步骤，推送到 GitHub 或在本机 Mac 上构建后才能拿到。
**未伪造任何安装记录。**

## 10. 后端能否运行

**能。** 实测启动命令与结果：

```bash
cd D:/ProjectLUMI
.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
# → Uvicorn running on http://127.0.0.1:8000
# → /api/v1/health: status=ok, database=ok, schema_version=2026102702, character_count=5
```

## 11. 是否完成真实模型对话

**否。** 未配置 `LUMI_API_KEY`，因此：
- 单元测试一律注入桩适配器（**永不调用真实模型，未产生任何费用**）；
- 端到端验证使用显式配置的 **Mock Provider**，其 `model` 固定为
  `mock-provider-v1` 并写入每条消息的 `model` 字段，`/health.is_mock=true`，
  回复文本里也自带「这是 Mock Provider 的固定话术」说明——**不可能被误认为真实模型输出**；
- 填入 `LUMI_API_KEY` 后即可切到 DeepSeek / OpenAI / 任意 OpenAI 兼容网关，
  代码路径已由 `test_provider_adapter.py`（15 项协议测试）覆盖。

## 12. Windows 与 iPhone 是否已经共享消息

**是（架构与接口层已实现并由自动化测试证明，且 Windows 侧实机跑通）。**

证据：
- `tests/test_sync.py` 9 项：用**两个不同的设备令牌**模拟 iPhone 与 Windows，
  验证共享会话、增量只返新增、`conv_seq` 单调、幂等重发不重复、
  tombstone 同步、人格一致、UTC 时间；
- `windows-bridge/lumi_bridge.py` 对真实运行的后端跑通
  `register → send → sync → memory → diary`；
- 服务端 SQLite 是唯一权威，两端都通过 API 读写。

**诚实边界**：iPhone 侧尚未在真机上运行过（未编译），
因此「iPhone 与 Windows 真实互通」还差最后一步**真机验证**。

## 13. 尚未解决的问题

1. iOS 编译 / IPA / 真机安装 —— 需 macOS 或 GitHub Actions；
2. 三套人格的原始设定文档缺失 —— 需你提供后覆盖；
3. 66 组语料与 data schema 缺失 —— 需你提供后补 JSONL 校验；
4. APNs 远程推送 —— 需付费开发者账号；
5. 桌宠进程内集成 —— 需桌宠源码；
6. 语音 / 图片 / 表情包 / Live2D —— 未实现，接口位置已预留；
7. 限流仍是单进程内存实现，多实例需换 Redis（v0.1 遗留）。

## 14. 下一阶段任务

按优先级：

1. **（你做）** 提供三套人格原始设计文档 → 覆盖 `characters` 表，`source` 改为 `builtin`；
2. **（你做）** 在 `.env` 填 `LUMI_API_KEY` → 打通真实模型对话；
3. **（你做）** 有 Mac 就 `xcodegen generate` 编译；否则 `git push` 触发 Actions 取 IPA；
4. **（我可续做）** 真实模型接通后的提示词调优与人格一致性回归测试；
5. **（我可续做）** 语音录制 / ASR / TTS（表与字段已预留）；
6. **（我可续做）** 图片消息与表情包（`media_assets` + `messages.media_id`）；
7. **（我可续做）** 流式回复（SSE），改善等待体验；
8. **（我可续做）** 拿到桌宠源码后做进程内集成。

---

## 附：本次开发始终遵守的硬约束

- ✅ 未询问用户任何问题、未索要密码或 API Key；
- ✅ 未购买付费服务、未开启收费 API、未写入任何密钥；
- ✅ 未删除、未覆盖既有工程与数据；数据库升级走原地迁移；
- ✅ 未强推、未改写 Git 历史；
- ✅ 未伪造测试通过、构建成功、真机安装或真实模型调用的任何记录。
