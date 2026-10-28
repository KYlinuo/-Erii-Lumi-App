# 开发状态

> 更新于 2026-10-28 · 版本 **v0.3.0**
> 本文只写**实际验证过的东西**。没跑过的一律标注为「未验证」，不写成"已完成"。

---

## 0. 一眼看懂的结论

| 问题 | 答案 |
|---|---|
| 后端能跑吗？ | ✅ 能。真实启动、真实读写、**164 项测试全过** |
| iOS 能编译吗？ | ✅ **已在 GitHub Actions 的 macOS Runner 上编译通过**，38 项 XCTest 全绿（模拟器） |
| 有 IPA 吗？ | ⚠️ CI 会产出**未签名 IPA** 工件，需用侧载工具重签后才能装 |
| 接真实模型了吗？ | ❌ 没有（无 API Key）。默认 Mock，回复会明确标记 |
| 语音能发吗？ | ⚠️ 客户端录音/播放代码完整；服务端**没有接真实 ASR/TTS**，转写返回「未接入」占位文本 |
| 图片能发吗？ | ✅ 上传、鉴权、去重、渲染链路完整，有 15 项测试 |
| Windows 能连吗？ | ✅ 桥接客户端实机跑通（注册→发消息→记忆→日记） |
| 桌宠改了吗？ | ❌ 没改。它是 Electron 发布包，无源码；改用桥接方案 |
| 数据会丢吗？ | ✅ 迁移只加列不删表；已用真实 v0.1 老库验证过原地升级 |

---

## 1. 功能矩阵

### 后端

| 能力 | 状态 | 证据 |
|---|---|---|
| FastAPI 启动 / 健康检查 | ✅ | `uvicorn` 实起，`/health` 返回 `version=0.3.0, schema_version=2026102801` |
| 版本化迁移（不删库） | ✅ | 真实 v0.1 老库升级后消息数不变（`docs/TEST_REPORT.md` §5） |
| 单用户 + 多设备身份 | ✅ | `test_devices.py` 8 项：注册、令牌鉴权、吊销、scope、改名 |
| 主令牌 / 设备令牌双轨 | ✅ | `test_auth.py` 10 项 |
| 请求限流 | ✅ | `test_ratelimit.py` 8 项（含 429 与 Retry-After） |
| 模型网关（OpenAI 兼容） | ✅ | `test_provider_adapter.py` 15 项，协议/超时/错误映射 |
| 重试 + Token 记账 | ✅ | `test_llm_gateway.py` 16 项 |
| Mock Provider | ✅ | 可追查（`model=mock-provider-v1`），不会悄悄顶替真实模型 |
| 人格系统（5 套） | ✅ | `test_personas.py` 13 项：互不合并、播种不覆盖 |
| 长期记忆（6 类 + 来源 + 可信度） | ✅ | `test_memory.py` 16 项，含三级隔离 |
| 跨设备同步 | ✅ | `test_sync.py` 9 项：双设备共享会话、增量、幂等、tombstone |
| 虚构人生（确定性生成） | ✅ | `test_world.py` 13 项：当天幂等、全部 `simulated` |
| 主动联系（时段/配额/免打扰） | ✅ | `test_proactive.py` 12 项；**不声称实现 APNs** |
| 媒体上传/下载/删除 | ✅ | `test_media.py` 15 项：魔数嗅探、大小上限、防穿越、去重 |
| 语音转写 / 合成 | ⚠️ | 接口与 Mock 完整；**未接真实服务** |
| 真实模型对话 | ❌ | 无 Key，全程零费用 |

### iOS 客户端（源码完成，未编译）

| 页面 / 能力 | 代码 | 编译验证 |
|---|---|---|
| 启动页（动画） | ✅ | ✅ 编译通过 |
| 聊天页（气泡/状态/重试/复制/Emoji） | ✅ | ✅ 编译通过 |
| 图片消息（相册选择、发送、渲染） | ✅ | ✅ 编译通过 |
| 语音消息（录音、播放、时长） | ✅ | ✅ 编译通过 |
| 人物主页 | ✅ | ✅ 编译通过 |
| 记忆页（来源/可信度标注） | ✅ | ✅ 编译通过 |
| 虚构日记页 | ✅ | ✅ 编译通过 |
| 设置页（服务器/令牌/同步） | ✅ | ✅ 编译通过 |
| 离线缓存 + 重启恢复 | ✅ | ✅ 有通过的单元测试 |
| 增量同步 + 幂等重发 | ✅ | ✅ 有通过的单元测试 |

**编译验证方式**：本机是 Windows，没有 Swift/iOS SDK，所以编译交给
GitHub Actions 的 `macos-15` Runner：XcodeGen 生成工程 → `xcodebuild test`
（iPhone 模拟器）→ 归档未签名 IPA。首轮构建暴露出 6 个真实缺陷，全部已修复，
现在 **38 项 XCTest 全部通过**。

本机另有 `scripts/swift_lint.py`（tree-sitter 语法解析）作为提交前的快速检查，
但它是语法级、不能替代真编译——这次的 6 个错误里它一个都没能发现。

### Windows 侧

| 能力 | 状态 |
|---|---|
| 桥接客户端（注册/发消息/记忆/日记） | ✅ 实机跑通 |
| 与 iPhone 共享同一角色与会话 | ✅ 双设备自动化测试证明 |
| 桌宠本体接入 | ⚠️ 提供契约与桥接，未改桌宠二进制 |
| 桌宠原有功能（动画/点击/文件传输） | ✅ 未触碰，保持原样 |

---

## 2. 构建与安装

### 2.1 后端

```bash
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r backend/requirements-dev.txt
cp .env.example .env
python scripts/gen_token.py --write
python scripts/run_backend.py
```

无 Key 也能跑：`LUMI_PROVIDER=mock`。

### 2.2 iOS —— 有 Mac

```bash
brew install xcodegen
cd frontend
xcodegen generate
open LUMI.xcodeproj
```

### 2.3 iOS —— 没有 Mac（CI 出未签名 IPA）

```bash
gh workflow run ios-build.yml
gh run watch
gh run download <run-id> -n LUMI-unsigned-ipa
```

产物 `LUMI-unsigned.ipa` 需要用 **SideStore / Sideloadly** 配自己的 Apple ID 重签后安装。
免费签名 7 天有效，且**不支持 APNs 远程推送**——这也是主动消息采用"服务端排队 +
打开 App 时拉取"的原因。

### 2.4 验证命令

```bash
python -m pytest -q          # 164 项
python scripts/swift_lint.py # iOS 语法检查
python scripts/smoke_test.py # 冒烟
```

---

## 3. 已知问题与限制

1. **iOS 只验证到「编译 + 单元测试」**。真机运行、权限弹窗、后台切换、弱网重连都还没在设备上试过。
2. **没有真实模型密钥**，所有"AI 回复"目前来自 Mock（会标注）。
3. **没有真实 ASR/TTS**，语音消息能被发送与播放，但转写内容是占位文本。
4. **免费签名不支持 APNs**，主动消息只在打开 App 时拉取。
5. **桌宠二进制未改造**，只能通过桥接客户端共享数据。
6. **`.xcodeproj` 不提交**，由 `project.yml` + XcodeGen 生成（避免两个事实来源）。
7. 仓库名以短横线开头（`-Erii-Lumi-App`），部分命令行工具会把它当作参数，
   克隆后请用 `cd ./-Erii-Lumi-App`。

---

## 3.1 持续集成实际抓到的 6 个缺陷

这些错误本机（Windows）无法发现，全部由 macOS Runner 首次真实编译暴露：

| # | 位置 | 问题 |
|---|---|---|
| 1 | `MemoryView.swift` | 单行字符串插值里换行写多语句表达式，Swift 不允许 |
| 2 | `ChatMessage.swift` | 非 Sendable 的 `ISO8601DateFormatter` 作 static let，违反 Swift 6 并发检查 |
| 3 | `MediaStore.swift` | `load()` 属于 `ConfigurationStore`，写成了 `ServerConfiguration.load()` |
| 4 | `ProfileView.swift` | `WrapLayout` 缺 `typealias Cache`，且 `placeSubviews` 参数顺序写错 |
| 5 | `LaunchView.swift` | `Animation.easeOut(delay:)` 不存在（delay 是修饰器） |
| 6 | `MessageStore.swift` | `save()` 未确保父目录存在，自定义路径写入直接 NSCocoaError Code=4 |

另外 CI 还抓到两个「本机能过、干净环境必挂」的依赖问题：
`python-dotenv` 版本漂移、`python-multipart` 未声明。

## 4. 分支约定

| 分支 | 用途 |
|---|---|
| `main` | 初始版本快照（v0.3.0，本次上传） |
| `workbuddy-dev` | 后续开发分支，AI 协作者的日常提交都落在这里 |

合并方向：`workbuddy-dev` → `main`，**不使用 force push**，不改写历史。

---

## 5. 下一步（按优先级）

1. 在 macOS / CI 上跑第一次 `xcodebuild test`，按真实报错修编译问题 → 产出 IPA
2. 填 `LUMI_API_KEY`，跑 `python scripts/smoke_test.py --real-model` 验证真实对话
3. 接入 ASR/TTS（填 `LUMI_ASR_MODEL` / `LUMI_TTS_MODEL`），把语音链路变成真的
4. 真机验证：录音权限、后台切换、耳机切换、弱网重连
5. 表情包与角色动画（当前只有静态头像与气泡）
