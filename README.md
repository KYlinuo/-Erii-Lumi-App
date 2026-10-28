# Project LUMI · Erii-Lumi-App

**绘梨衣桌宠 × AI 女友一体化工程** —— 原生 iOS（Swift 6 / SwiftUI）+ 自托管后端
（Python / FastAPI / SQLite）+ Windows 桥接客户端，共用同一套角色、会话、记忆与虚构人生。

> 仓库：<https://github.com/KYlinuo/-Erii-Lumi-App>
> 当前版本：**v0.3.0**　后端测试：**164 项全部通过**　开发分支：`workbuddy-dev`

**先说清楚现状**：后端 **164 项测试全绿**（本地 + GitHub Actions 双环境）；
iOS 已在 `macos-15` Runner 上**真实编译通过**，**38 项 XCTest 全绿**（模拟器）；
但**从未在真机上跑过**，也没有签名后的可安装包。所有未验证项都在
[DEVELOPMENT_STATUS.md](DEVELOPMENT_STATUS.md) 里逐条列明，不含任何美化。

| 持续集成 | 状态 |
|---|---|
| Backend Tests (Ubuntu) | [![Backend Tests](https://github.com/KYlinuo/-Erii-Lumi-App/actions/workflows/backend-tests.yml/badge.svg)](https://github.com/KYlinuo/-Erii-Lumi-App/actions/workflows/backend-tests.yml) |
| iOS Build (macOS) | [![iOS Build](https://github.com/KYlinuo/-Erii-Lumi-App/actions/workflows/ios-build.yml/badge.svg)](https://github.com/KYlinuo/-Erii-Lumi-App/actions/workflows/ios-build.yml) |

---

## 这是什么

一个「同一个 AI 角色，多个设备」的系统：

- **iPhone** 上是一个原生 SwiftUI App（聊天 / 人物主页 / 记忆 / 虚构日记 / 设置）
- **Windows** 上通过桥接客户端（或用桌宠自己的方式）接入
- **服务器**是唯一权威：消息、长期记忆、虚构人生时间线都存在这里

角色不是客服。5 套人格（LUMI / 林穗 / 祁鹿 / 沈昼 / 绘梨衣）各有稳定性格、说话方式、
虚构背景，互不合并；她记得你说过的事，也有自己的"生活"，但**虚构内容与你的真实信息
在数据库层面强制隔离**，界面和接口都会标注。

---

## 目录结构

```
.
├── backend/                 FastAPI 后端
│   ├── app/
│   │   ├── main.py          应用装配、lifespan（先建表/迁移，再播种）
│   │   ├── migrations.py    版本化迁移（老库原地升级，绝不删库）
│   │   ├── models.py        10 张表：users / devices / characters / conversations /
│   │   │                    messages / memory_records / world_events / media_assets /
│   │   │                    proactive_messages / device_cursors
│   │   ├── services.py      编排：幂等 → 人格 → 落库 → 记忆吸收 → 上下文 → 调用 → 落库
│   │   ├── personas.py      5 套人格（可扩展，播种不覆盖既有设定）
│   │   ├── memory.py        长期记忆：六分类 + 来源 + 可信度 + 三级隔离
│   │   ├── world.py         虚构人生：确定性生成、当天幂等、全部标记 simulated
│   │   ├── proactive.py     主动联系：时段/配额/免打扰/即时关闭
│   │   ├── media.py         媒体库：魔数嗅探、大小上限、内容哈希去重
│   │   ├── speech.py        ASR / TTS 适配（含 Mock，明确标注未接入）
│   │   ├── identity.py      用户与设备身份
│   │   ├── security.py      主令牌 + 设备令牌，作用域校验
│   │   ├── llm/             模型网关（OpenAI 兼容 + Mock + 重试）
│   │   └── routers/         health / chat / conversations / devices / characters /
│   │                        memory / world / sync / proactive / media
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   └── deploy/              部署样例
├── frontend/                iOS 客户端
│   ├── LUMI/                Swift 源码（App / Models / Services / ViewModels / Views）
│   ├── LUMITests/           XCTest（含媒体解码与向后兼容用例）
│   └── project.yml          XcodeGen 工程定义（Windows 上可维护）
├── windows-bridge/          Windows 桥接客户端（纯标准库，实机跑通）
├── tests/                   pytest（164 项）
├── scripts/                 环境自检 / 起服务 / 冒烟 / Swift 静态检查 / 发布脚本
├── docs/                    PRD、架构细节、API、变更日志、测试报告、交付报告
├── .github/workflows/       iOS 构建（macOS Runner）+ 后端测试
├── ARCHITECTURE.md          架构总览（根目录）
├── DEVELOPMENT_STATUS.md    已实现 / 未完成 / 构建方法（根目录）
└── .env.example             配置示例（只含占位符，无真实凭据）
```

---

## 快速开始（后端）

```bash
git clone https://github.com/KYlinuo/-Erii-Lumi-App.git
cd ./-Erii-Lumi-App         # 仓库名以短横线开头，用 ./ 前缀避免被当成参数

python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r backend/requirements-dev.txt

cp .env.example .env
python scripts/gen_token.py --write  # 生成访问令牌写入 .env
# 编辑 .env：填 LUMI_API_KEY（真实模型密钥，只放后端）
```

启动：

```bash
python scripts/run_backend.py
# 健康检查 http://127.0.0.1:8000/api/v1/health
# 接口文档 http://127.0.0.1:8000/docs
```

**没有 API Key 也能跑**：`LUMI_PROVIDER=mock` 会走 Mock Provider，
回复里带 `model=mock-provider-v1` 标记，不会伪装成真实模型。

验证：

```bash
python -m pytest -q                       # 164 项
python scripts/smoke_test.py              # 冒烟（真实模型项会 SKIP）
python scripts/swift_lint.py              # iOS 源码语法检查（无需 macOS）
```

---

## iOS 客户端

**需要 macOS**（或 GitHub Actions 的 macOS Runner）：

```bash
brew install xcodegen
cd frontend
xcodegen generate
open LUMI.xcodeproj          # 连真机，选开发者账号直接运行
```

没有 Mac 就用 CI 出**未签名 IPA**（侧载工具重签后安装）：

```bash
gh workflow run ios-build.yml
gh run watch
gh run download <run-id> -n LUMI-unsigned-ipa
```

详细步骤与坑位见 [DEVELOPMENT_STATUS.md](DEVELOPMENT_STATUS.md)。

### 连接后端

App → 设置 → 服务器地址填 `http://<电脑局域网 IP>:8000`（或已部署的 HTTPS 域名）→
访问令牌填 `.env` 里的 `LUMI_ACCESS_TOKEN` → 点「重新检测」。

---

## 安全约定

- **模型密钥只在服务端** `.env`；客户端、构建产物里都没有。
- `.env`、`*.db`、`*.pem`、`*.p12`、`*.mobileprovision`、`*.ipa` 全部 gitignore。
- 设备令牌在服务端只存 `SHA256(token + 盐)`，注册时明文只返回一次。
- 上传的媒体按 magic bytes 嗅探真实类型（不信任客户端 MIME），磁盘文件名由服务端生成。
- 公开部署请务必 `LUMI_ENV=prod`（强制认证）+ HTTPS，且不要放入任何真实聊天数据。

---

## 文档

| 文档 | 内容 |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 架构总览与关键设计决策 |
| [DEVELOPMENT_STATUS.md](DEVELOPMENT_STATUS.md) | **哪些能用、哪些没做、怎么构建** |
| [docs/API.md](docs/API.md) | HTTP 接口、错误码、同步协议 |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | 版本变更 |
| [docs/TEST_REPORT.md](docs/TEST_REPORT.md) | 实测结果（含未验证项） |
| [docs/ERII_INTEGRATION.md](docs/ERII_INTEGRATION.md) | 与绘梨衣桌宠的整合方式 |
| [docs/NEXT_MORNING.md](docs/NEXT_MORNING.md) | 接手者第一天该做什么 |
| [docs/PRD.md](docs/PRD.md) | 产品需求与验收状态 |

---

## 许可与素材

角色设定、台词、形象均为本项目原创或用户自有素材，不包含未经授权的第三方角色图片与音乐。
代码目前未声明开源许可，默认保留所有权利。
