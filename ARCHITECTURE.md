# 架构总览

本文是**根目录的入口级架构说明**；更细的设计决策在
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)，接口细节在 [docs/API.md](docs/API.md)。

---

## 一句话

**服务端是唯一权威，客户端只是视图。** iPhone 与 Windows 不各自维护记忆库，
所有会话、消息、长期记忆、虚构人生都只写在服务器的 SQLite 里，两端靠增量游标同步。

---

## 分层

```
┌──────────────────────────┐        ┌──────────────────────────┐
│  iOS (Swift 6 / SwiftUI) │        │  Windows 桥接 / 桌宠      │
│  ChatView / MemoryView   │        │  lumi_bridge.py           │
│  DiaryView / ProfileView │        │  (标准库，无第三方依赖)    │
└────────────┬─────────────┘        └────────────┬─────────────┘
             │  HTTPS + X-LUMI-TOKEN             │
             └───────────────┬───────────────────┘
                             ▼
┌──────────────────────────────────────────────────────────────┐
│  FastAPI  /api/v1                                            │
│  health · chat · conversations · sync · memory · world        │
│  characters · devices · proactive · media · speech            │
├──────────────────────────────────────────────────────────────┤
│  services.py        业务编排（幂等 → 人格 → 落库 → 记忆 → 生成）│
│  personas.py        5 套人格，可扩展，互不合并                  │
│  memory.py          长期记忆 + 三级隔离 + 来源/可信度           │
│  world.py           虚构人生（确定性生成，不花钱）              │
│  proactive.py       主动联系调度（服务端排队 + 客户端拉取）      │
│  media.py / speech.py  媒体库与语音适配（含 Mock）              │
│  llm/               模型网关：OpenAI 兼容 + Mock + 重试 + 记账   │
├──────────────────────────────────────────────────────────────┤
│  SQLite（10 张表）+ 版本化迁移（migrations.py，绝不删库）        │
└──────────────────────────────────────────────────────────────┘
```

---

## 五个关键设计决策

### 1. 迁移而不是重建

`migrations.py` 里每个步骤带版本号，记录在 `schema_migrations`，执行前先查列是否已存在。
所有步骤幂等，只做 `ADD COLUMN` / `CREATE INDEX`，**没有任何 DROP/DELETE**。

实测：一个连 `schema_migrations` 表都没有的 v0.1 老库，启动 v0.3 后自动补列、
原有消息一条不丢（见 `docs/TEST_REPORT.md` 第 5 节）。

### 2. 幂等靠 `request_id`，不靠时间

客户端为每条消息生成 `request_id` 并持久化；重试沿用同一个 ID。
服务端 `UNIQUE(request_id)`，重复提交直接返回上次的回复（`idempotent_replay=true`）。

**踩过的坑**：早期用"这条用户消息之后的第一条助手消息"来定位上次回复，
结果第二轮的请求会匹配到第一轮的回复，被误判成重放而跳过模型。
现已改为按 `request_id` 精确绑定，并有回归测试守着。

### 3. 同步靠 `conv_seq`，不靠时间戳

每条消息在会话内有单调递增的 `conv_seq`；客户端只需上报"我读到第几号"，
服务端返回大于它的所有消息。跨设备、断线重连、乱序到达都不会错位。
删除是软删除（`deleted_at`），tombstone 也会同步过去。

### 4. 记忆分三层，物理隔离

| subject | 含义 | 可见范围 |
|---|---|---|
| `user` | 用户真实信息（"我叫阿泽""不吃香菜"） | 跨人格共享 |
| `relationship` | 某段关系里的共同经历 | 按 `character_id` 隔离 |
| `character` | 角色的虚构人生 | 按 `character_id` 隔离，且永不写进用户事实 |

每条记忆都带 `source_type`（explicit / inferred / world_simulation）与 `confidence`。
**推断出来的内容不会被当成你说过的话**，注入提示词时也会带"（推测，不确定）"。

### 5. 没接的东西就说没接

- 没有 `LUMI_API_KEY` → 走 Mock Provider，`model` 字段写 `mock-provider-v1`
- 没有 `LUMI_ASR_MODEL` → 转写返回「（语音消息 · N 秒；本机未接入 ASR，未做转写）」
- 没有 `LUMI_TTS_MODEL` → 返回可播放的合成 WAV，响应头 `X-LUMI-Mock: true`
- 主动联系默认关闭；免费签名不支持 APNs，所以采用「服务端排队 + 打开 App 时拉取」

宁可显示"没接"，也不给一个看起来成功、实际是假的体验。

---

## 数据模型（10 张表）

| 表 | 作用 | 要点 |
|---|---|---|
| `users` | 单用户主体 | 当前产品形态只有一个用户 |
| `devices` | 设备 | 令牌只存 `SHA256(token + 盐)`，可单独吊销、可限定 scope |
| `device_cursors` | 每设备同步游标 | 记录"读到第几号"，支持断点续传 |
| `characters` | 人格 | 5 套内置，`source` 标明来源，播种只补空字段 |
| `conversations` | 会话 | 绑定人格与来源设备 |
| `messages` | 消息 | `request_id` 幂等、`conv_seq` 游标、`kind`（text/image/audio）、`media_id`、Token 记账、软删除 |
| `memory_records` | 长期记忆 | 六分类 + 来源 + 可信度 + 三级隔离 |
| `world_events` | 虚构人生 | 全部 `simulated=true`，带时间戳与心情 |
| `media_assets` | 媒体 | 内容哈希去重，磁盘按哈希分桶 |
| `proactive_messages` | 主动消息 | 排队、投递状态、可即时撤销 |

---

## 客户端结构（iOS）

```
LUMI/
├── App/          LUMIApp / RootView（5 个 Tab）/ AppSession（全局状态）
├── Models/       ChatMessage / ServerModels / PersonaModels / MediaModels / LUMIError
├── Services/     LUMIAPIClient（唯一网络入口）/ MessageStore（本地缓存）
│                 KeychainStore / ServerConfiguration / AudioKit / MediaStore
├── ViewModels/   ChatViewModel / PersonaViewModel / MemoryViewModel
│                 DiaryViewModel / SettingsViewModel
└── Views/        ChatView / ProfileView / MemoryView / DiaryView / SettingsView
                  MessageBubble / ComposerBar / LaunchView / LUMIStyle
```

约定：

- 网络只走 `LUMIAPIClient`，错误统一转成 `LUMIError`（带中文可展示文案）
- 令牌只在 Keychain，`ServerConfiguration` 负责读取
- 聊天消息先写本地（`MessageStore`）再发网络，断网也能看到历史
- 所有 ViewModel 标注 `@MainActor`，模型类型 `Sendable`，符合 Swift 6 严格并发

---

## 与绘梨衣桌宠的关系

桌宠是 **Electron 发布包，没有源码**，其内置 AI 模块是"文件整理任务"而不是陪伴对话，
无法直接改造。因此本项目采取：

1. 保留桌宠原有功能，**不动它的任何文件**；
2. 通过 `windows-bridge/lumi_bridge.py` 让它接入统一后端，共享同一角色与会话；
3. 绘梨衣的人格设定与 168 句原创台词已提取进 `backend/app/resources/`，作为她的语料。

细节见 [docs/ERII_INTEGRATION.md](docs/ERII_INTEGRATION.md)。
