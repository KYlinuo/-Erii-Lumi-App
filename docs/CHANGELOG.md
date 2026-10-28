# Changelog

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本遵循语义化版本。

## [0.3.0] - 2026-10-28（第二阶段夜间开发）

### Added — 后端

- **媒体库** `backend/app/media.py`：图片 / 语音 / 表情上传、下载、删除。
  安全约束全部有测试：magic bytes 嗅探（不信任客户端 MIME）、单文件上限
  （图片 8 MiB / 语音 20 MiB，超限 413）、服务端生成文件名（`../../evil.png` 无效）、
  内容哈希去重（同图只占一份磁盘）
- **语音适配层** `backend/app/speech.py`：ASR / TTS 的 OpenAI 兼容适配器 +
  Mock 实现。未配置时返回 `mock=true`，TTS 的 Mock 会生成**真正可播放的 WAV**，
  让客户端播放链路在零成本下可验证
- 新增接口：`POST/GET/DELETE /api/v1/media`、`/media/{id}/transcribe`、
  `/api/v1/speech/tts`、`/api/v1/speech/transcribe`、`/api/v1/speech/status`
- 聊天支持媒体：`POST /chat` 接受 `media_id` + `kind`，
  voice-only 时正文由转写补全；图片没有视觉模型时插入明确说明，不让模型"凭空看图"
- 迁移 `2026102801`：`messages.kind`（text/image/audio）+ 媒体索引

### Added — iOS

- **录音** `AudioRecorder`（AVAudioRecorder / m4a AAC / 电平动画 / 120s 上限 / 权限申请）
- **播放** `AudioPlayer`（同刻只播一条，进度回调）
- **媒体缓存** `MediaStore`（按 media_id 缓存 + 并发去重，滚动不会重复下载）
- 输入栏新增「相册」与「麦克风」，图片/语音气泡可在聊天流里直接渲染与播放
- `ChatMessage` 增加 `kind` / `mediaID` / `localMediaPath` / `durationMs`，
  本地文件保证上传前即可预览、重启后仍可离线查看
- 失败重试支持媒体消息（本地文件还在就重新上传）
- Info.plist 补 `NSMicrophoneUsageDescription` / `NSPhotoLibraryUsageDescription`
- 新增 `LUMITests/MediaDecodingTests.swift`（7 项，含 v0.2 后端兼容回退）

### Added — 工程

- `scripts/swift_lint.py`：Windows 上的 Swift 静态检查
  （tree-sitter 语法解析 + 括号配平 + 顶层重复声明），33 个文件全部通过
- `scripts/github_publish.ps1`：一键推 GitHub 并触发 iOS 构建（需人工点一次 Authorize）
- `windows-bridge` 之外新增 `scripts/relay_converse.py`：由 Agent 充当模型跑通
  真实多轮对话（9 轮，4 个人格，验证了记忆注入与幂等）

### Fixed

1. `_find_previous_reply` 用时间戳匹配回复，会把上一轮回复误判成本轮 → 改为
   通过 `request_id` 精确绑定（由 9 轮 relay 对话暴露）
2. `Message.to_dict()` 是 v0.1 兼容视图，不含 `kind`/`media_id`，
   导致媒体消息在历史接口里退化成纯文本 → 补齐字段
3. `ChatRequest.message` 的 `min_length=1` 让"纯语音消息"直接 422 → 改为允许空串，
   由业务层判断"既无文字又无媒体"才报错
4. Swift 静态检查发现并修复了 `ChatViewModel` 中媒体重试路径的遗漏

### 已知限制

- iOS 仍未在本机编译（Windows 无 Swift / iOS SDK）；语法级检查已通过
- 未接入真实 ASR / TTS 服务（无密钥，全程零费用）
- GitHub 推送需人工授权一次（App-Bound 加密 + 设备码，见 NEXT_MORNING）

## [0.2.0] - 2026-10-28（夜间开发）

### Added — 后端

- **版本化数据库迁移** `backend/app/migrations.py`：老库原地升级，记录在 `schema_migrations`，
  每个步骤幂等；**绝不允许通过删库解决结构问题**（4 项迁移测试覆盖，含 v0.1 老库数据保全）
- 数据模型扩到 10 张表：`users` `devices` `device_cursors` `characters` `conversations`
  `messages` `memory_records` `world_events` `media_assets` `proactive_messages`
- **身份与设备**：设备注册、每设备独立令牌（服务端只存加盐 SHA-256）、作用域、吊销
- **模型网关**：退避重试（只对超时/断连/限流重试）、Token 消耗记账、
  Mock Provider（`model=mock-provider-v1`，可在 `/health.is_mock` 与消息的 `model` 字段追查）
- **人格系统** `personas.py`：LUMI / 林穗 / 祁鹿 / 沈昼 / 绘梨衣，可扩展、互不合并；
  播种只补空字段，**不会覆盖既有设定**
- **长期记忆** `memory.py`：六分类 + 来源 + 可信度；`subject` 三级隔离
  （用户事实跨人格共享 / 关系记忆按人格隔离 / 角色虚构人生独立）
- **虚构人生** `world.py`：日记 / 爱好 / 阅读进度 / 关系 / 目标时间线，
  确定性生成（不消耗任何额度），同一天幂等，全部标记 `simulated=true`
- **主动联系** `proactive.py`：允许时段、每日上限、最小间隔、夜间免打扰、即时关闭；
  采用「服务端排队 + 客户端拉取」，**未实现也不声称实现了 APNs**
- **跨设备同步**：`conv_seq` 单调游标、`request_id` 幂等去重、软删除 tombstone、
  设备游标；新增 `/sync`、`/sync/conversation/{id}`、`/sync/cursor`
- 新增路由：`/devices` `/characters` `/memory` `/world` `/sync` `/proactive`
- Windows 桥接客户端 `windows-bridge/lumi_bridge.py`（纯标准库，实机跑通）

### Added — iOS 客户端

- 新增**人物主页** `ProfileView`、**记忆页** `MemoryView`、**虚构日记页** `DiaryView`
- `RootView` 改为 TabView：聊天 / 人物 / 记忆 / 日记 / 设置
- 统一设计规范 `LUMIStyle.swift`（柔和光影 + 玻璃质感 + 深色）
- `ChatViewModel`：幂等重发（复用 `request_id`）、增量同步、主动消息补拉
- 传输模型全部向后兼容 v0.1 后端（`decodeIfPresent` + 显式成员构造器）

### Fixed（测试发现的真实缺陷）

1. 幂等重发在「首次请求上游失败」时触发 `UNIQUE(request_id)` 崩溃 → 复用已落库消息重试，跨会话返回 409
2. SQLite 丢失 tzinfo 导致 `created_at` 没有 `+00:00` → 新增 `UTCDateTime` 类型装饰器
3. 真实启动报 `no such table: users`（lifespan 只播种未建表）→ lifespan 先 `create_all()` 再 `bootstrap()`
4. `bootstrap` 用 `created_at == updated_at` 判新建，恒为 0 → 改为显式查重
5. Swift `ChatMessage` 是值类型，原地修改丢失 → 改为按下标写回数组
6. 虚构世界记忆被误标为「推测」→ 拆分为 `isInferred` / `isSimulated`
7. 虚构日记出现重复句子 → 当天严格幂等 + 7 天窗口内避免复述

### Changed

- `security.py`：`verify_token` 返回 `Caller`（身份 + 作用域），支持主令牌与设备令牌
- `models.py`：消息新增 `request_id` / `conv_seq` / `client_ts` / `media_id` / tokens / `deleted_at`
- `services.py`：编排顺序 = 幂等 → 人格 → 落库用户消息(commit) → 记忆吸收 → 上下文 → 带重试调用 → 落库回复

### Security

- 设备令牌服务端只存 `SHA256(token + salt)`，注册时明文只返回这一次
- 模型 API Key 仍只在服务端；客户端零密钥
- 新增 403/409 错误码：权限不足与幂等冲突都有明确语义

### 已知限制

- iOS 编译 / IPA **未在本机验证**（Windows 无 Swift/iOS SDK）
- 未做过真实模型调用（无 API Key），本次未产生任何 API 费用
- 主动联系默认关闭
- 语音 / ASR / TTS / 图片消息尚未实现（数据表与字段已预留）

## [0.1.0] - 2026-10-26

### Added

**后端（Python / FastAPI / SQLite）**
- FastAPI 服务：`/api/v1/chat`、`/api/v1/conversations`、`/api/v1/health`、`/api/v1/persona`
- SQLAlchemy 模型 `Conversation` / `Message`，SQLite WAL 持久化，删除会话级联删消息
- OpenAI 兼容模型适配器，首个接入 DeepSeek（`LUMI_PROVIDER_BASE_URL` 可指向任意兼容网关）
- 上游错误细分 7 种错误码（超时/断网/认证/限流/坏响应/未配置/未知），统一错误信封
- 单用户访问认证（`X-LUMI-TOKEN` / `Bearer`），生产环境无 token 拒绝启动
- 内存滑动窗口限流，`chat`（10/min）与 `default`（30/min）分作用域
- 用户消息先落库再调模型：上游失败不丢用户输入
- 未配置 API Key 时返回 503 `provider_not_configured`，不伪造回复
- HTTPS 部署配置：nginx 反代（TLS 终结 + 安全头）与 systemd 服务单元

**iOS 客户端（Swift 6 / SwiftUI）**
- 原生启动页：LUMI 形象动画 + 服务器探测
- 独立 AI 少女形象：SwiftUI 矢量头像 `LUMIAvatar` + 程序化生成的 App Icon
- 聊天 UI：气泡、打字指示、错误条、失败重试、滚动到底
- 设置页：服务器地址 / 超时 / 令牌管理 / 连接状态实时检测 / 历史同步 / 清除本地数据
- 令牌存 Keychain（`AfterFirstUnlockThisDeviceOnly`），客户端零模型密钥
- 本地消息持久化（actor + JSON 原子写），冷启动恢复历史；损坏文件自动隔离
- 7 类错误码 → 独立中文提示与重试建议；断网/超时/限流可区分

**构建与工程**
- XcodeGen `project.yml`（可在 Windows 维护的 Xcode 工程配置）
- GitHub Actions：macOS-15 runner 跑模拟器单测 + 模拟器构建 + 真机未签名 IPA
- GitHub Actions：Ubuntu 跑后端 pytest
- `scripts/`：check_env / gen_token / run_backend / smoke_test / gen_assets
- 测试：54 项后端单元测试 + iOS 端 XCTest（模型/持久化/错误映射/解码）

### Security
- 模型 API Key 仅存于后端环境变量；`.env` 与一切凭据被 gitignore
- `/health` 只返回脱敏密钥指纹
- 后端限流 + 单用户认证默认开启；客户端不写入任何模型密钥

### 已知限制
- 限流为单进程内存实现，多实例需换 Redis
- 聊天为非流式返回
- iOS 编译只能在 macOS / CI 执行
