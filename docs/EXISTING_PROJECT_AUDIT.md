# 现有工程审计报告

> 审计时间：2026-10-27 23:05 – 2026-10-28 01:00（北京时间）
> 审计对象：Project LUMI（iPhone AI 少女）与 绘梨衣桌宠（Windows）
> 审计方式：**以磁盘上真实存在的文件为准**，不因「曾被规划」就认定已实现。

---

## 1. 工程定位结果

| 项目 | 真实位置 | 版本控制 | 源码可得性 |
|---|---|---|---|
| Project LUMI | `D:/ProjectLUMI` | Git，`master`/HEAD `eeee84f`，3 次提交 | ✅ 完整源码 |
| 绘梨衣桌宠 | `D:/绘梨衣/EriiPet-Windows-x64-2.2.4-preview.1/` | 无仓库 | ❌ **只有发布包，没有源码** |
| 当前工作区 | `C:/Users/KYlinuo/WorkBuddy/APP` | — | 空目录（无任何文件） |

审计基线：`git rev-parse HEAD = eeeee84f7e3a6a4aa6ad0756da2e1a73e21f20bb2`，
工作区干净（`git status --porcelain` 为空），不存在未提交修改需要抢救。
开发分支：`night/v0.2`（从 `eeee84f` 切出，未改写任何既有历史）。

---

## 2. Project LUMI v0.1 实际具备的功能（已核实）

### 后端（Python / FastAPI / SQLite）
- FastAPI 应用：`/api/v1/chat`、`/conversations`、`/health`、`/persona`、`/time`
- SQLAlchemy 模型 `Conversation` / `Message`，SQLite WAL，级联删除
- OpenAI 兼容适配器（`openai_compat.py`），默认指向 DeepSeek
- 上游错误细分 7 种错误码 + 统一错误信封 `{"error":{code,message,hint}}`
- 单用户认证（`X-LUMI-TOKEN` / `Bearer`），生产环境强制 token
- 内存滑动窗口限流（`chat` 10/min、`default` 30/min）
- 「用户消息先落库再调模型」「未配置 Key 返回 503 不伪造回复」两条硬约束
- nginx / systemd 部署配置

### iOS 客户端（Swift 6 / SwiftUI）
- 19 个 Swift 源文件：启动页、聊天页、气泡、输入条、设置页、矢量形象、App Icon
- Keychain 存令牌、本地 JSON 快照持久化、7 类错误中文提示
- XcodeGen `project.yml`（Windows 可维护）+ 2 个 GitHub Actions 工作流

### 测试
- 54 项 pytest **全部通过**（本机实测复现）
- 3 个 XCTest 文件

### v0.1 明确**不具备**的能力（本次夜间任务要补的）
- 多设备身份 / 设备令牌 / 会话权限
- `User` / `Device` / `Character` / `MemoryRecord` / `WorldEvent` / `MediaAsset` 表
- 消息的幂等 ID、同步游标、发送状态
- 增量同步 / 跨设备去重 / 离线恢复
- 数据库迁移（v0.1 只能 `create_all`，改结构必须删库）
- 人格系统、长期记忆、虚构人生、主动联系
- 人物主页 / 记忆页 / 虚构日记页

---

## 3. 绘梨衣桌宠实际具备的功能（已核实）

目录 `D:/绘梨衣/` 保存了 1.1.0 → 2.2.4 共 14 个发布包，最新为
`EriiPet-Windows-x64-2.2.4-preview.1`。包内可直接读取的文档说明了已实现能力：

- 桌宠角色动画（24 种形态 / 18 种动作，`萌版绘梨衣.eriipet` 中记录）
- 点击互动、动态启动界面（微光开场、五款抽卡式开场）
- 跨设备文件互传、远程访问（`CONNECT_API_CONTRACT.md` / `NAS_API_CONTRACT.md`）
- AirPods 互联（`AIRPODS_API_CONTRACT.md`）
- 本地 AI 任务（**文件整理类**，不是陪伴对话）
- 168 句原创悄悄话（`绘梨衣-168句悄悄话.txt`，本项目原创短句）

### 关键发现（直接影响整合方案）
1. **发布包是 Electron 应用**：包内存在 `EriiPet.exe`、`chrome_100_percent.pak`、
   `LICENSES.chromium.html` 等 Chromium 运行时文件；
   **没有 Node/JS 源码**（未随包分发），因此**无法**在桌宠进程内直接改造它的对话模块。
2. **它的 AI 接口不是陪伴对话**：`AI_API_CONTRACT.md` 描述的 `/api/ai/v1/tasks`
   是「文件搜索 / 阅读 / 整理 / 计划」的任务型接口，
   与 LUMI 的「人格聊天 + 长期记忆 + 虚构人生」语义不同，不能简单互调。
3. 文档明确写道：「原生客户端边界……SwiftUI 可复用相同版本 API 及任务模型，
   但**原生配对/安全存储尚待开发**」——即官方也承认移动端接入未完成。

### 结论：整合走「同一后端 + 桥接客户端」而非「改桌宠源码」
见 `docs/ERII_INTEGRATION.md`。本仓库交付了真实可运行的 Windows 桥接客户端
`windows-bridge/lumi_bridge.py`，与 iPhone 共用同一角色 ID、同一会话、
同一消息库、同一记忆、同一虚构时间线。

---

## 4. 未找到的既有资料（BLOCKED，需人工补齐）

以下资料在本次可访问的磁盘范围内**没有找到**，因此没有被当成"已存在"：

| 资料 | 搜索范围 | 结果 |
|---|---|---|
| 林穗 / 祁鹿 / 沈昼 的原始人格设计文档 | `WorkBuddy`、`ProjectLUMI`、`绘梨衣`、`Documents`、`Downloads` | ❌ 未找到 |
| 66 组中文聊天测试语料 | 同上 | ❌ 未找到 |
| `Project_LUMI_data_schema.json` | 同上 | ❌ 未找到 |
| Project LUMI 人物设计 Markdown | 同上 | ❌ 未找到 |
| Codex 桌宠工程源码 | `D:/绘梨衣`、`Documents/Codex` | ❌ 只有发布包 |

**处理方式（如实、不伪造）**：
- 三套人格已按「可扩展人格引擎」实现，但 `source` 标记为 `reconstructed`，
  接口与 UI 都会显式提示「设定待补充」，**绝不冒充原始设定**；
- 绘梨衣的设定来自桌宠包内真实素材（`绘梨衣-168句悄悄话.txt` + `.eriipet` 描述），
  `source = "erii-pet"`，并且播种逻辑**只补空字段、绝不覆盖已有内容**；
- 待你提供原始文档后，只需更新 `characters` 表或直接编辑
  `backend/app/personas.py` 中的 `BUILTIN_CHARACTERS`，其余链路无需改动。

---

## 5. 保护性措施（本次开发前已执行）

1. 记录分支与 Commit ID（见本报告第 1 节）；
2. 备份运行期数据库：`D:/ProjectLUMI/.night-backup/lumi.db.<时间戳>.bak`；
3. 建立独立开发分支 `night/v0.2`，**未**强推、未改写 Git 历史、未删除任何文件；
4. 数据库升级走**版本化原地迁移**（`backend/app/migrations.py`），
   实测对 v0.1 老库升级后 3 条历史消息原封不动（`tests/test_migrations.py`）；
5. 未触碰 `D:/绘梨衣` 下任何文件（只读了文档与文本素材）；
6. 未购买任何服务、未开启付费 API、未写入任何密钥。

---

## 6. 可直接复用的成熟模块（本次选择保留而非重写）

| 模块 | 决策 |
|---|---|
| `llm/openai_compat.py` | **保留**，只在其之上加重试与 Token 记账 |
| `llm/errors.py` 7 类错误映射 | **保留**，新增业务错误另开 `errors.py` |
| `ratelimit.py` 滑动窗口 | **保留**，仅补充新端点的 scope |
| `services.append_message` / 上下文组装 | **保留**并扩展（历史条数、排除当前消息等既有修正全部保留） |
| `Views/LUMIAvatar.swift` 矢量形象 | **保留**，人物主页直接复用 |
| `Services/KeychainStore.swift` | **保留** |
| `scripts/*.py` | **保留** |
