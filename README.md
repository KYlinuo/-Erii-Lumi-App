# 绘梨衣 Erii 2.1.1

2026-10-30 更新，iOS build 22。原生 SwiftUI 聊天客户端 + FastAPI 后端，沿用 Erii 2.1.0 源码和数据。本次侧重删冗余、降低滚动/图片开销、补 iOS 27.2 / ProMotion 验收流程。

本轮后端 279 项测试通过；56 个 Swift 文件静态检查无阻断，存在 4 条已人工核对的枚举提示。当前环境没有 Xcode，未验证本版编译、XCTest、自签安装、真机帧率与耗电。旧版 CI 成功不能代表本版成功。

## 先读

- [本版修改、测试和限制](docs/RELEASE_2.1.1.md)
- [下一轮五小时 WorkBuddy 提示词](docs/WORKBUDDY_5H_PROMPT.md)
- [iOS 27.2 与高刷验收](docs/PERFORMANCE_ACCEPTANCE.md)
- [接手步骤](docs/HANDOFF.md)
- [长期功能矩阵](docs/FEATURE_MATRIX.md)

## 运行后端

需要 Python 3.11+。在解压后的项目根目录创建虚拟环境并安装依赖：

```bash
python -m venv .venv
# macOS / Linux：source .venv/bin/activate
# Windows PowerShell：.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements-dev.txt
```

复制 `.env.example` 为 `.env`，填写自己的服务端访问令牌和模型配置，执行：

```bash
python scripts/check_env.py
python scripts/run_backend.py
```

默认监听 `127.0.0.1:8000`；手机连接电脑上的后端时，需按实际网络配置监听地址，并在 App 中填写手机可访问的地址。手机的 `127.0.0.1` 指向手机本身。访问令牌只填 App 的服务器设置，模型 API Key 只保留在后端。当前默认模型提供方为 deepseek；没有有效配置不会自动提供真实模型回复。自动测试使用独立测试库和桩服务。

本私人交接包保留原始 `backend/data/lumi.db`；没有 `.env` 或 `backend/.env`，只有 `.env.example`。运行真实库前应使用 SQLite backup API 做一致备份；开发验证优先使用副本。公开分发前需排除私人数据库和运行数据。

## 质量检查

```bash
python scripts/audit_source.py
python -m ruff check backend/app --select F401,F841
python -m pytest -q
python scripts/swift_lint.py
```

Swift 静态脚本是轻量启发式检查，另有本轮 tree-sitter 语法解析记录；两者都不是 Swift 编译器。实际执行证据位于 `docs/validation/`。

## iOS 编译与安装

`frontend/project.yml` 是 XcodeGen 工程来源，保留 `com.projectlumi.LUMI` 和 iOS 17 兼容下限。主验收系统为 iOS 27.2；设备型号、屏幕能力和系统 build 需实际记录。

在配有对应 SDK 的 Mac 上安装 XcodeGen，执行 `bash scripts/ios_validate.sh`。设置 `ERII_TEST_DESTINATION='platform=iOS Simulator,id=实际UDID'` 可运行 XCTest；不设置时脚本在完成构建后返回 3，表示测试未完成。再用自己的签名方案安装到真机。包内没有冒充新版的旧 IPA。

ProMotion 已启用 opt-in；系统动画、Tab 和导航按系统节奏运行。高刷是硬件及系统允许时的目标，不保证全局锁定 120fps。具体实测标准见性能验收文档。

## WorkBuddy 技能

项目内 `.codebuddy/skills/erii-ios-quality/` 是可复用技能源文件，独立技能 ZIP 可通过 WorkBuddy 的技能上传入口导入。桌面版是否自动发现项目路径需要实际检查；本次没有远程安装到你的 WorkBuddy。即使未导入，也可让它直接读取 SKILL.md 和提示词执行。

原有记忆、约定、虚构日常、学习/共读等模块保留。接口存在不等于 iOS 界面已接通，状态以新版功能矩阵与实际运行证据为准。
