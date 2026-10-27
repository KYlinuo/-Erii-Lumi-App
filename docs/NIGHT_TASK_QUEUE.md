# 夜间任务队列

状态标记：`TODO` / `IN_PROGRESS` / `DONE` / `BLOCKED`

## 一、审计与保护

| # | 任务 | 状态 | 证据 |
|---|---|---|---|
| 1 | 定位两个工程的真实位置 | DONE | `D:/ProjectLUMI`（Git）、`D:/绘梨衣`（发布包） |
| 2 | 记录分支与 Commit ID | DONE | `master` @ `eeee84f` |
| 3 | 备份运行期数据库 | DONE | `.night-backup/lumi.db.20261027-230719.bak` |
| 4 | 建立独立开发分支 | DONE | `night/v0.2` |
| 5 | 验证 v0.1 基线测试 | DONE | 54/54 通过（改造前实测） |
| 6 | 读取桌宠已有设定 | DONE | 168 句悄悄话 → `backend/app/resources/erii_whispers.json` |
| 7 | 查找三套人格原始文档 | **BLOCKED** | 磁盘上不存在，已按"待补充"实现并显式标注 |

## 二、统一 AI 后端

| # | 任务 | 状态 | 证据 |
|---|---|---|---|
| 8 | 版本化数据库迁移（不删库） | DONE | `migrations.py` + `tests/test_migrations.py`（4 项） |
| 9 | 扩展数据模型至 10 张表 | DONE | `models.py` |
| 10 | 用户 / 设备 / 设备令牌 / 作用域 | DONE | `identity.py` + `routers/devices.py` + 8 项测试 |
| 11 | 模型网关：重试 + 退避 | DONE | `llm/retry.py` + 3 项测试 |
| 12 | Mock Provider（无 Key 联调） | DONE | `llm/mock.py`，`model=mock-provider-v1` 可追查 |
| 13 | Token 消耗记录 | DONE | `messages.tokens_prompt/completion` + 测试 |
| 14 | 人格系统提示词 / 记忆注入 | DONE | `personas.compose_system_prompt` + 测试 |
| 15 | DeepSeek / OpenAI / Gemini 切换 | DONE（接口层） | OpenAI 兼容协议，改环境变量即可；**未做真机调用**（无 Key） |

## 三、人格与长期记忆

| # | 任务 | 状态 | 证据 |
|---|---|---|---|
| 16 | 可扩展人格引擎 + 5 套人格 | DONE | `personas.py` + 11 项测试 |
| 17 | 不覆盖绘梨衣既有设定 | DONE | `seed_characters` 只补空字段（有测试） |
| 18 | 记忆六分类 + 来源 + 可信度 | DONE | `memory.py` + 17 项测试 |
| 19 | 用户事实与角色虚构严格隔离 | DONE | `subject` 三级隔离（有测试） |
| 20 | 记忆编辑 / 删除 / 导出接口 | DONE | `routers/memory.py` |
| 21 | 66 组语料转 JSONL 并校验 | **BLOCKED** | 语料文件不存在（见审计第 4 节） |

## 四、跨设备同步

| # | 任务 | 状态 | 证据 |
|---|---|---|---|
| 22 | 消息幂等 ID + 同步游标 | DONE | `request_id` / `conv_seq` |
| 23 | 增量同步接口 | DONE | `POST /api/v1/sync`、`GET /sync/conversation/{id}` |
| 24 | 软删除 tombstone 同步 | DONE | 有测试 |
| 25 | 双设备共享会话自动化测试 | DONE | `tests/test_sync.py` 9 项（iPhone + Windows 两个令牌） |
| 26 | UTC 时间统一 | DONE | `UTCDateTime` 类型装饰器（**修复了 SQLite 丢失 tzinfo 的缺陷**） |

## 五、虚构人生与主动联系

| # | 任务 | 状态 | 证据 |
|---|---|---|---|
| 27 | 虚构日记 / 爱好 / 阅读 / 关系 / 目标 | DONE | `world.py` + 12 项测试 |
| 28 | 事件确定性生成（不花额度） | DONE | `world.simulate_day` 幂等且可回放 |
| 29 | 主动联系调度（时段/配额/免打扰/即时关闭） | DONE | `proactive.py` + 13 项测试 |
| 30 | APNs 远程推送 | **BLOCKED** | 免费自签不支持，文档与接口均声明 `apns_remote_push=false` |

## 六、iOS 原生 App

| # | 任务 | 状态 | 证据 |
|---|---|---|---|
| 31 | 人物主页 | DONE（源码） | `Views/ProfileView.swift` |
| 32 | 记忆页面 | DONE（源码） | `Views/MemoryView.swift` |
| 33 | 虚构日记页面 | DONE（源码） | `Views/DiaryView.swift` |
| 34 | 启动页 / 聊天页 / 设置页 | DONE（v0.1 已有，v0.2 增强） | 新增 Tab 导航、同步、幂等重发 |
| 35 | 统一设计规范 | DONE | `Views/LUMIStyle.swift` |
| 36 | **真机编译验证** | **BLOCKED** | Windows 无 Swift/iOS SDK，需 macOS 或 GitHub Actions |
| 37 | IPA 生成 | **BLOCKED** | 同上；workflow 已配置未签名 IPA 步骤 |

## 七、语音与高级交互

| # | 任务 | 状态 | 证据 |
|---|---|---|---|
| 38 | 语音录制 / ASR / TTS | TODO（未开始） | 时间分配让位于核心链路；`MediaAsset` 表与接口已预留 |
| 39 | 图片消息 / 表情包 | TODO（未开始） | `media_assets` 表与 `messages.media_id` 已预留 |
| 40 | Live2D / 3D | TODO（按指令"暂不强制"） | 预留 `media_assets.kind` |

## 八、绘梨衣桌宠整合

| # | 任务 | 状态 | 证据 |
|---|---|---|---|
| 41 | 保护桌宠既有功能 | DONE | 未触碰 `D:/绘梨衣` 任何文件 |
| 42 | 统一 AI 后端对接 | DONE（桥接层） | `windows-bridge/lumi_bridge.py`，实机跑通 |
| 43 | 桌宠进程内集成 | **BLOCKED** | 无源码（Electron 发布包），见 `ERII_INTEGRATION.md` |
| 44 | 共享角色/会话/记忆/时间线 | DONE | 桥接与 iPhone 走同一 `character_id` / `conversation_id` |

## 九、构建、测试与交付

| # | 任务 | 状态 | 证据 |
|---|---|---|---|
| 45 | 后端全量测试 | DONE | **144/144 通过** |
| 46 | 真实服务器启动验证 | DONE | uvicorn 实测启动，桥接客户端跑通全链路 |
| 47 | GitHub Actions 配置 | DONE | 两条 workflow 已加 `night/**` 触发 |
| 48 | 交付文档 | DONE | 本报告 + NIGHT_REPORT + NEXT_MORNING 等 |
| 49 | Git 提交 | DONE | 见 `NIGHT_REPORT.md` |
| 50 | iOS 真机 / Actions 构建 | **BLOCKED** | 需 macOS 或已推送到 GitHub |

---

## BLOCKED 清单汇总（需第二天人工处理）

1. **三套人格原始设计文档缺失** → 提供文档后覆盖 `characters` 表即可。
2. **66 组聊天语料 & `Project_LUMI_data_schema.json` 缺失** → 提供文件后补充 JSONL 校验脚本。
3. **iOS 编译 / IPA** → 需要 macOS 本机 Xcode，或把仓库推送到 GitHub 触发 Actions。
4. **APNs 远程推送** → 需要付费 Apple 开发者账号，当前方案是"服务端排队 + 客户端拉取"。
5. **桌宠进程内集成** → 需要 Codex 桌宠源码仓库。
6. **真实模型调用** → 需要配置 `LUMI_API_KEY`（本次未产生任何 API 费用）。
