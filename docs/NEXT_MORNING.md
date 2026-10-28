# 第二天早上要看的说明（中文，说人话版）

> 生成时间：2026-10-28 凌晨 · 分支 `night/v0.2`
> 下面每一条都是**昨晚真实跑出来**的结果。没做到的地方我会直接写"没做到"。

---

## 一、昨晚到底做完了什么

**一句话**：iPhone 和 Windows 现在可以共用同一个 AI 少女大脑了——
同一个角色、同一份聊天记录、同一份长期记忆、同一条虚构生活时间线。

具体新增/改造：

- **后端**（`D:/ProjectLUMI/backend`）：加了**数据库迁移**（老库原地升级，不删数据）、
  多设备身份（每台设备一个令牌，可单独吊销）、人格系统、长期记忆、
  虚构人生、跨设备增量同步、主动联系排队。
- **iPhone App**（`D:/ProjectLUMI/frontend`）：从一个只有聊天页的 App，
  变成有 **聊天 / 人物 / 记忆 / 虚构日记 / 设置** 五个页面的完整 App。
- **Windows 桥接**（`D:/ProjectLUMI/windows-bridge/lumi_bridge.py`）：
  一个能直接跑的命令行客户端，让 Windows 侧读写同一份数据。
- **测试**：从 54 项增加到 **144 项，全部通过**。

---

## 二、有没有一个"真正能跑"的 App？

**后端：能跑，我已经真机跑过了。**
启动命令（在项目目录下）：

```bash
cd D:/ProjectLUMI
.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

然后打开 http://127.0.0.1:8000/docs 能看到全部接口。
昨晚我实际启动过，并用桥接客户端完整跑了一遍注册→聊天→记忆→日记。

**iPhone App：代码写完了，但还没有编译过。**
这是最重要的一句实话：**Windows 上没有 Swift 编译器，也没有 iOS SDK，
所以我没法验证它能编译通过、更没法生成 IPA。**
代码是按 Swift 6 严格并发规范写的，但"能编译"这件事要等你：
- 在 Mac 上打开（见第五节），或
- 把仓库推到 GitHub 触发 Actions（workflow 已经配好，会自动跑模拟器测试 + 尝试打包未签名 IPA）。

**Windows 桌宠：我改不了它。**
桌宠只有发布包没有源码（是 Electron 打包的），所以我**没有动它任何一个文件**，
而是另外交付了一个桥接客户端来共用同一个大脑。详见 `ERII_INTEGRATION.md`。

---

## 三、怎么连 AI 后端（让 AI 真正开口说话）

现在后端默认是 **Mock 模式**（我故意的）——它会回一句固定话术，
并且每句回复都会带上"（这是 Mock Provider 的固定话术…）"，
这样你一眼就能看出这不是真模型说的，不会被骗。

要换真模型：

1. 打开 `D:/ProjectLUMI/.env`（没有就复制 `.env.example`）
2. 填一行：`LUMI_API_KEY=sk-你的密钥`
3. 想用别家模型就再加：
   - DeepSeek（默认）：`LUMI_PROVIDER_BASE_URL=https://api.deepseek.com`
   - OpenAI：`LUMI_PROVIDER_BASE_URL=https://api.openai.com`、`LUMI_PROVIDER_MODEL=gpt-4o-mini`
   - 任意 OpenAI 兼容网关（含本地 vLLM / Ollama）同理
4. 重启后端。`/api/v1/health` 里 `is_mock` 会变成 `false`。

**重要**：昨晚**没有配置任何 Key，也没有产生一分钱 API 费用**。

---

## 四、怎么启动 Windows 开发环境

```bash
cd D:/ProjectLUMI
# 1) 起后端（另开一个终端，保持运行）
.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --port 8000

# 2) 跑全部测试（144 项）
.venv/Scripts/python.exe -m pytest -q

# 3) 用桥接客户端试聊
set LUMI_BASE_URL=http://127.0.0.1:8000
python windows-bridge/lumi_bridge.py register --name "My PC"
python windows-bridge/lumi_bridge.py send "你好"
```

数据库文件在 `backend/data/lumi.db`。我已经备份过一份在
`.night-backup/lumi.db.20261027-230719.bak`。

---

## 五、怎么拿到 iOS 安装包

**现在拿不到**，因为没编译过。两条路：

### 路线 A：有 Mac（推荐，最快）
```bash
cd D:/ProjectLUMI/frontend
brew install xcodegen      # 只装一次
xcodegen generate          # 由 project.yml 生成 LUMI.xcodeproj
open LUMI.xcodeproj
```
在 Xcode 里选你的 iPhone 17 Pro → Run。首次需要在
Settings → Privacy & Security 里信任开发者证书。

### 路线 B：用 GitHub Actions（不用 Mac 也能拿 IPA）
```bash
cd D:/ProjectLUMI
git remote add origin <你的仓库地址>
git push -u origin night/v0.2
```
推送后 Actions 会自动跑：XcodeGen → 模拟器单测 → 模拟器构建 →
**未签名 IPA**（产物在 Actions 页面的 Artifacts 里下载）。
未签名 IPA 需要用 **Sideloadly / AltStore / SideStore** 配合你的免费 Apple ID 侧载，
**7 天过期**，需要重签。

### 安装到 iPhone（侧载流程概述）
1. 下载 `LUMI-unsigned.ipa`
2. 电脑装 Sideloadly，登录你的 Apple ID
3. 数据线连 iPhone，选 IPA → Start
4. iPhone 上：设置 → 通用 → VPN 与设备管理 → 信任该开发者
5. 打开 App 后先在「设置」页填服务器地址（比如 `http://192.168.x.x:8000`）
   和访问令牌

> 注意：手机和电脑要在同一个局域网；用 `http` 时 iOS 可能要求
> 在 Info.plist 里允许明文流量（工程里已经按开发需要配置好，
> 正式使用请上 HTTPS，配置见 `backend/deploy/nginx-lumi.conf`）。

---

## 六、现在哪些能用、哪些还不能

### ✅ 能用（已实测）
- 后端启动、健康检查、会话与消息读写
- 多设备注册与令牌认证、设备吊销
- 5 个人格（LUMI / 林穗 / 祁鹿 / 沈昼 / 绘梨衣）切换
- 长期记忆自动抽取（名字、喜好、计划、待续话题），带"推测/用户说过"标记
- 虚构日记（确定性生成，不花额度，明确标为虚构）
- 跨设备增量同步、幂等重发、软删除同步
- 主动联系排队（默认关闭，可随时一键取消）
- Windows 桥接客户端全流程

### ⚠️ 部分可用
- **真实模型对话**：代码接好了，但没有 Key，没做过真实调用。
- **人格设定**：LUMI 和绘梨衣有真实素材；林穗/祁鹿/沈昼是**我先按你给的名字
  气质写的初版**，界面上标了"设定待补充"——你把原始设计文档给我，
  我直接覆盖进去，不会动其他代码。

### ❌ 还没做
- iOS 真机安装 / IPA（需要 Mac 或 GitHub）
- APNs 远程推送（免费自签不支持，现在只能是"服务端排队 + App 自己来取"）
- 语音录制 / ASR / TTS、图片消息、表情包（数据表和接口位置已预留）
- Live2D / 3D 形象（按你的指令"暂时不强制"）
- 桌宠进程内的对话替换（缺源码）

---

## 七、第二天必须人工做的最少操作（按优先级）

1. **（5 分钟，最重要）** 把三套人格的原始设计文档放进项目里，
   我（或你自己）更新 `backend/app/personas.py` 里的
   `BUILTIN_CHARACTERS`，把 `source` 从 `reconstructed` 改成 `builtin`。
2. **（5 分钟）** 在 `.env` 里填 `LUMI_API_KEY`，重启后端——这是让 AI 真正说话的唯一一步。
3. **（10 分钟）** 有 Mac 就 `xcodegen generate` 编译一次；
   没有就 `git push` 触发 Actions 拿构建结果。**这一步不做的話，
   iPhone 上跑不起来。**
4. **（可选）** 把仓库推到 GitHub 前，确认 `.env` 没有被提交
   （`.gitignore` 已排除，但推送前值得瞄一眼）。
5. **（可选）** 如果你能拿到 Codex 桌宠源码，按 `ERII_INTEGRATION.md` 第 5 节
   把它的对话出口指向后端。

---

## 八、几个你可能想立刻知道的细节

- **聊天记录会不会丢？** 不会。用户消息在调用模型**之前**就写进数据库了，
  就算模型那边超时或断网，你说过的话都还在。
- **会不会偷偷用假回复骗我？** 不会。没配 Key 时后端返回明确的 503
  `provider_not_configured`；就算开了 Mock，回复里也会写明是 Mock，
  并且每条消息都记录了 `model` 字段（Mock 叫 `mock-provider-v1`），随时可查。
- **iPhone 和 Windows 看到的历史会不一致吗？** 不会。服务端是唯一权威，
  两边都靠 `conv_seq` 增量拉取，重复提交还有 `request_id` 去重。
- **虚构日记会不会被当成我的真实经历？** 不会。数据库里 `subject` 分了三层，
  角色的虚构人生和你的真实信息物理隔离，接口和界面也都带明确标注。

---

# 更新（v0.3）：现在还多了语音和图片

## 新增可用能力

- **发图片**：聊天页输入框左边的「相册」按钮，选图即发。图片先存到手机本地
  （气泡立刻显示），再上传到服务器；断网时那张图还在，点「重试」会重新上传。
- **发语音**：点麦克风录音，再点方块结束。录音上限 2 分钟。
- **听语音**：如果服务器接了 TTS，可以让角色把回复读出来。

## 关于「语音识别」

现在**没有接真实的语音识别**（没有密钥）。所以发语音时，服务端会回一句
「（语音消息 · N 秒；本机未接入 ASR，未做转写）」。这是**故意**的：宁可显示"没接"，
也不假装听懂了。想真正用起来，在 `.env` 里加：

```
LUMI_ASR_MODEL=whisper-1
LUMI_TTS_MODEL=tts-1
LUMI_TTS_VOICE=alloy
```

（OpenAI 兼容的模型名，换成你用的服务商对应的名字即可。）

## 怎么拿到 iOS 安装包（这是唯一还需要你动手的地方）

这台机器上没有 Mac，也没法离线编译 iOS。工程已经写好，两条路：

**A. 有 Mac**（最省事）

```bash
brew install xcodegen
cd frontend
xcodegen generate
open LUMI.xcodeproj      # 连上 iPhone，选你的开发者账号直接跑
```

**B. 没有 Mac，用 GitHub Actions 出未签名 IPA**

在 `D:\ProjectLUMI` 打开一个命令行窗口，运行仓库里的 `scripts/github_publish.ps1`
（右键「使用 PowerShell 运行」也可以）。

脚本会：检查工作区 → 让你在浏览器点一次 Authorize → 建私有仓库 → 推代码 →
触发 macOS 构建。构建完成后：

```bash
gh run watch
gh run download <run-id> -n LUMI-unsigned-ipa
```

拿到 `LUMI-unsigned.ipa` 后，用 **SideStore / Sideloadly** 配合你自己的免费 Apple ID
重签安装（免费签名 7 天有效，且**不支持** APNs 远程推送——所以我们才用
「服务端排队 + 打开 App 时拉取」的方式做主动消息）。

> 为什么这一步不能全自动：Windows 对浏览器的登录态做了 App-Bound 加密，
> 别的进程拿不到你的 GitHub cookie；GitHub 的设备码授权也必须由人点一次同意。
> 这是安全设计，不是代码问题。

## 我怎么确认代码没写错

Windows 上没有 Swift 编译器，所以我在 `scripts/swift_lint.py` 里用 tree-sitter
做了真实语法解析（33 个 Swift 文件）+ 括号配平 + 顶层重复声明检查，目前全部通过。
**但这只是语法级**，类型和 SwiftUI 视图构建必须等 macOS 那次构建才知道。
