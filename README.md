<div align="center">

# Project LUMI

**会一直在你身边的 AI 少女 · v0.1**

原生 iOS (Swift 6 / SwiftUI) + 自托管后端 (Python / FastAPI / SQLite / DeepSeek)

</div>

---

## 项目结构

```
ProjectLUMI/
├── backend/            FastAPI 后端（app/ 源码, deploy/ 部署配置）
├── frontend/           iOS 客户端
│   ├── LUMI/           Swift 源码 + 资源
│   ├── LUMITests/      XCTest 单元测试
│   └── project.yml     Xcode 工程定义（Windows 可维护）
├── docs/               PRD / 架构 / API / 变更日志 / 测试报告
├── tests/              后端 pytest 测试
├── scripts/            环境自检 / 令牌生成 / 启动 / 冒烟测试 / 资源生成
└── .github/workflows/  iOS 构建 + 后端测试 CI
```

## 快速开始（后端）

### 1. 安装依赖

```bash
cd ProjectLUMI
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r backend/requirements-dev.txt
python scripts/check_env.py     # 环境自检
```

### 2. 配置环境变量

```bash
cp .env.example .env
python scripts/gen_token.py --write   # 生成访问令牌并写入 .env
```

然后编辑 `.env`，填入唯一的真实凭据：

```ini
LUMI_API_KEY=sk-你的DeepSeek密钥     # 只放后端！
LUMI_ACCESS_TOKEN=（gen_token 已写入）
LUMI_ENV=dev                         # 上线改 prod
```

### 3. 启动

```bash
python scripts/run_backend.py
# 健康检查 http://127.0.0.1:8000/api/v1/health
# 接口文档 http://127.0.0.1:8000/docs
```

### 4. 验证

```bash
python -m pytest -q                              # 54 项单元测试
python scripts/smoke_test.py --real-model        # 端到端（真实调用模型，产生少量费用）
```

## iOS 客户端

### 构建（需要 macOS 或 GitHub Actions）

```bash
brew install xcodegen
cd frontend
xcodegen generate          # project.yml → LUMI.xcodeproj
open LUMI.xcodeproj        # Xcode 中 Cmd+R 运行
```

命令行构建三种产物：

```bash
# 模拟器
xcodebuild -project LUMI.xcodeproj -scheme LUMI \
  -destination 'platform=iOS Simulator,name=iPhone 16' build

# 真机（未签名 IPA，供侧载工具）
xcodebuild archive -project LUMI.xcodeproj -scheme LUMI \
  -destination 'generic/platform=iOS' -archivePath build/LUMI.xcarchive \
  CODE_SIGNING_ALLOWED=NO CODE_SIGN_IDENTITY=""
cd build && cp -R LUMI.xcarchive/Products/Applications/LUMI.app Payload/ \
  && zip -qry LUMI-unsigned.ipa Payload
```

也可以直接推送到 GitHub，Actions 会自动产出：

- `LUMI-simulator-app`（模拟器 .app）
- `LUMI-unsigned-ipa`（未签名 IPA，用 AltStore / Sideloadly / TrollStore 安装）
- `lumitest-results`（XCTest 结果）

### 连接后端

1. App 首页 → 右上角齿轮进入设置；
2. 「服务器地址」填后端地址：
   - 同一 Wi-Fi 下真机调试：`http://<电脑局域网IP>:8000`
   - 已部署 HTTPS：`https://lumi.example.com`
3. 「访问令牌」填 `.env` 里的 `LUMI_ACCESS_TOKEN`（自动存入 Keychain）；
4. 点「重新检测」，看到「已连接」即可返回聊天。

## 安全约定

- **模型 API Key 只存在于后端** `.env`；客户端代码、配置、构建产物中都没有密钥。
- `.env`、`*.pem`、`*.mobileprovision` 等一律被 gitignore，`scripts/check_env.py` 会验证。
- 客户端令牌保存于 iOS Keychain，不参与 iCloud 备份。
- 公开部署请务必：`LUMI_ENV=prod`（强制认证）+ HTTPS（见 `backend/deploy/`）。
- 未经允许不得公开部署任何带私人聊天数据的服务。

## 文档

| 文档 | 内容 |
|------|------|
| [docs/PRD.md](docs/PRD.md) | 产品需求与验收状态 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 架构与关键设计决策 |
| [docs/API.md](docs/API.md) | HTTP 接口与错误码 |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | 版本变更 |
| [docs/TEST_REPORT.md](docs/TEST_REPORT.md) | 实测测试结果 |

## 路线图

- v0.2：流式回复（SSE）、多会话管理、语音
- v0.3：长期记忆、主动问候、表情动作
