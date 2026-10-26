# Changelog

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本遵循语义化版本。

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
