# 绘梨衣桌宠整合方案与现状

> 本文如实记录"Windows 桌宠接入统一 AI 后端"做到了什么、没做到什么。

---

## 1. 结论先行

| 目标 | 状态 | 说明 |
|---|---|---|
| 保护桌宠既有功能 | ✅ 完成 | 本次开发**未写入/修改** `D:/绘梨衣` 下任何文件 |
| 共享同一角色 ID | ✅ 完成 | 两端都使用 `characters.key = "erii"` 绑定会话 |
| 共享同一会话 | ✅ 完成 | 同一 `conversation_id`，Windows 与 iPhone 读写同一份消息 |
| 共享同一消息数据库 | ✅ 完成 | 服务端 SQLite 为唯一权威，两端都通过 API 读写 |
| 共享同一长期记忆 | ✅ 完成 | `subject='user'` 跨人格共享；`erii` 的关系记忆按人格隔离 |
| 共享同一虚构人生时间线 | ✅ 完成 | `world_events.character_id` 一致，两端看到的日记相同 |
| **在桌宠进程内替换对话模块** | ❌ **未完成（BLOCKED）** | 桌宠无源码（Electron 发布包） |

---

## 2. 为什么无法在桌宠进程内集成

1. `D:/绘梨衣/EriiPet-Windows-x64-2.2.4-preview.1/` 是**发布产物**：
   内含 `EriiPet.exe`、`chrome_100_percent.pak`、`LICENSES.chromium.html`
   等 Chromium 运行时文件，可判定为 **Electron 应用**；
2. 包内 **没有 Node/JS 源码**（未随包分发，`integrations/` 下只有 MCP/任务相关脚本）；
3. 它的 `AI_API_CONTRACT.md` 描述的是 `/api/ai/v1/tasks`——
   **文件搜索 / 阅读 / 整理 / 计划**的任务型接口，语义是"帮我整理文件"，
   不是"陪我聊天的 AI 少女"；两者不能简单互调。

因此，"让桌宠接入统一 AI 后端"只能以**桥接**方式实现：
桌宠侧（或任何 Windows 脚本）调用桥接客户端，桥接客户端访问 LUMI 后端。

---

## 3. 已交付的桥接客户端

`windows-bridge/lumi_bridge.py` —— 纯 Python 标准库，无需安装依赖。

```bash
set LUMI_BASE_URL=http://<你的后端地址>:8000

python windows-bridge/lumi_bridge.py status                 # 后端与本机注册状态
python windows-bridge/lumi_bridge.py register --name "EriiPet Windows"
python windows-bridge/lumi_bridge.py characters             # 列出人格
python windows-bridge/lumi_bridge.py send "今天过得怎么样"    # 使用 erii 人格
python windows-bridge/lumi_bridge.py sync                   # 增量拉取（含 iPhone 端消息）
python windows-bridge/lumi_bridge.py diary --character erii
python windows-bridge/lumi_bridge.py memory --character erii
```

- 注册后令牌写入 `.lumi_device.json`（权限 600）；服务端只存加盐 SHA-256，
  数据库泄露也无法还原令牌。
- 默认人格 `erii`（可用 `LUMI_CHARACTER` 覆盖）。

### 实机验证记录（2026-10-28）

后端：`uvicorn app.main:app`（Mock Provider），桥接客户端实测输出：

```
已注册设备 EriiPet Windows（windows）
  设备 ID    : 6b4802118b6d4fd887600d464f214e89
  权限       : chat, memory, sync, world

  lumi       LUMI
  linsui     林穗  ⚠ 设定待补充
  shenzhou   沈昼  ⚠ 设定待补充
  qilu       祁鹿  ⚠ 设定待补充
  erii       绘梨衣  （来自桌宠设定）

[erii] 你：我叫小林，我很喜欢在夜里写代码
[erii] mock-provider-v1：收到。关于我叫小林…
  conversation_id = 31bc87ec98d24f9f90277bc46b321194  conv_seq = 2

共 4 条记忆（人格 erii 可见范围）
  · [user_fact/user] 用户的名字是 小林（推测，55%）
  · [user_preference/user] 用户喜欢 在夜里写代码（推测，55%）
  · [fictional_life/character] 一天结束时会把「今天还不错的瞬间」悄悄收起来（角色设定，100%）
  · [fictional_life/character] 她随身带一个小本子，想到什么就写下来（角色设定，100%）

【绘梨衣 的虚构日记】以下为角色虚构生活中的内容，不是真实经历…
```

---

## 4. 桌宠素材已被保留并复用

- `绘梨衣-168句悄悄话.txt`（168 句本项目原创短句）
  → 抽取为 `backend/app/resources/erii_whispers.json`
  → 通过 `GET /api/v1/characters/erii/idle-lines` 对外提供，
  返回体带 `fictional: true` 与说明文字，**不会被当成真实经历**。
- `萌版绘梨衣.eriipet` 中的描述（24 种形态 / 18 种动作 / 小本子日常陪伴）
  已写入绘梨衣人格的 `background` 与 `interests`。
- 播种逻辑 `personas.seed_characters()` **只补空字段**，
  如果你日后把更完整的设定写进 `characters` 表，重启也不会被覆盖（有测试保证）。

---

## 5. 要让桌宠"真正用上"还需要什么（第二天人工项）

1. 拿到 Codex 桌宠的源码仓库（或让 Codex 侧开放一个"对话提供者"配置）；
2. 在桌宠中把"AI 闲聊"出口指向桥接客户端，或在桌宠内直接实现下列契约；

### 集成测试契约（桌宠侧只需满足这几条）

| 契约 | 要求 |
|---|---|
| 角色 | 使用 `character_key = "erii"`，不得自行另建一套人设 |
| 会话 | 复用服务端返回的 `conversation_id`，不要本地另建一套会话 |
| 幂等 | 每次发送带 `request_id`，重试时**必须复用同一个 ID** |
| 时间 | 一律 UTC，展示时再转本地时区 |
| 同步 | 断线恢复后用 `POST /api/v1/sync` 按 `conv_seq` 增量补齐 |
| 虚构内容 | 日记/待机台词必须标注为虚构，不得混入用户真实信息 |

对应的自动化验证已经在 `tests/test_sync.py` 里用两个设备令牌跑通，
桌宠接入后可直接复用同一套断言。
