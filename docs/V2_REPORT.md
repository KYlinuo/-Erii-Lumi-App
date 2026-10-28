# Project LUMI v2.0 阶段报告

> 更新时间：2026-10-29
> 分支：`workbuddy-dev`　基线：`a85747b` / `e5ebe8b`
> 本文件只写**实际发生的事**；没做的功能明确写在"未完成"里，不冒充已完成。

---

## 一、最关键的发现：黑边不是布局问题，是 plist 被覆盖

真机截图里 App 只占屏幕中间一条、上下大片黑色、字体被系统等比放大 —— 这是 iOS 的
**兼容模式（letterbox）**，不是 SwiftUI 布局写错。

排查过程：

1. 解包已安装的 `LUMI-unsigned.ipa`，读出 `Payload/LUMI.app/Info.plist`；
2. 发现包里**没有** `UILaunchScreen`、`UISupportedInterfaceOrientations`、
   `CFBundleIconName`、`UIApplicationSceneManifest`，版本号还是 `1.0`；
3. 对照仓库里手写的 `frontend/LUMI/Info.plist`（这些键都在）→ 说明打包时被替换了；
4. 定位到 `frontend/project.yml` 的 `info: path: LUMI/Info.plist`：
   **XcodeGen 会按生成的默认内容重写该路径下的文件**，把手写键全部抹掉；
5. iOS 拿不到启动屏声明 → 判定为不支持新屏幕的老应用 → 以兼容模式运行。

修复：

| 文件 | 改动 |
|---|---|
| `frontend/project.yml` | 删除 `info:` 块；改用 `INFOPLIST_FILE: LUMI/Info.plist`；`sources` 里排除该文件避免被当资源重复打包 |
| `frontend/LUMI/Info.plist` | 版本号改为 `$(MARKETING_VERSION)` / `$(CURRENT_PROJECT_VERSION)` |
| `frontend/project.yml` | `MARKETING_VERSION` 2.0.0 / `CURRENT_PROJECT_VERSION` 20 |

> 验证方式：构建后重新解包 IPA，确认 `Info.plist` 里的 `UILaunchScreen` 存在。
> 这一步在 CI 中执行（见第五节），**没有真机确认前不要宣称黑边已消失**。

---

## 二、Mock 话术泄漏（截图中第二条回复）

截图里 AI 说：*"……那就慢慢来吧，反正在我这里不用着急。（这是 Mock Provider 的固定话术，用于无 Key 环境下的管线联调。）"*

问题有两层：

1. 调试说明被写进了**回复正文**，等于角色本人在说"我是假人"；
2. 气泡下方直接显示 `mock-provider-v1` 模型名。

修复：

| 文件 | 改动 |
|---|---|
| `backend/app/llm/mock.py` | 删除塞进正文的 `_QUESTION_TAIL`；Mock 身份改由字段表达 |
| `backend/app/schemas.py` | `ChatResponse` 新增 `is_mock: bool` |
| `backend/app/services.py` | 两处返回值按 `model.startswith("mock-")` 填 `is_mock` |
| `frontend/LUMI/Models/ServerModels.swift` | `ChatResponse.isMock` |
| `frontend/LUMI/Models/ChatMessage.swift` | `ChatMessage.isMock` |
| `frontend/LUMI/ViewModels/ChatViewModel.swift` | Mock 回复不再写入 model 名；带 `isMock` |
| `frontend/LUMI/Views/MessageBubble.swift` | 改为橙色小字「演示回复 · 未接入模型」 |

---

## 三、唯一人格：绘梨衣

| 文件 | 改动 |
|---|---|
| `backend/app/config.py` | `default_character_key` 由 `lumi` 改为 `erii` |
| `frontend/LUMI/ViewModels/ChatViewModel.swift` | 默认 `characterKey` 改为 `erii` |
| `tests/test_chat.py`、`test_llm_gateway.py`、`test_personas.py` | 断言不再写死某个角色名，改为跟随默认人格 |

说明：其他人格（林穗/祁鹿/沈昼/LUMI）**没有删除**，`characters` 表与历史数据保持原样，
只是前台不再默认进入。真要物理移除需要单独做数据归档，不在本次范围。

---

## 四、聊天界面与外观（已完成）

| 文件 | 内容 |
|---|---|
| `Views/BubbleTheme.swift`（新） | 樱色微光 / 深夜星河 / 透明冰晶三套主题，**只提供样式参数** |
| `Services/AppearanceStore.swift`（新） | 主题、背景图（模糊/亮度/遮罩）、双方头像，落 Application Support |
| `Views/AppearanceSettingsView.swift`（新） | 主题切换、背景选择与滑杆、头像选择/清除 |
| `Views/ModelStatusView.swift`（新） | 直接显示"模型尚未配置 / 已接入真实模型" |
| `Views/MessageBubble.swift`（重写） | 双方头像、引用条、长按菜单（复制/引用/重发/删除）、图片全屏预览、连续消息合并头像 |
| `Views/ChatView.swift`（重写） | 分组与时间分隔、引用状态、全屏预览、顶部头像与通话入口 |
| `Views/ComposerBar.swift`（重写） | 引用条、表情条、图片/语音/发送三态切换 |
| `Views/ProfileView.swift` | 去掉多人物切换，改为绘梨衣单人格 + 换头像 |
| `Views/SettingsView.swift` | 新增「外观与气泡」「AI 模型」两个入口 |

通话按钮不做假界面：点开是**真实能力说明页**（读取 `/speech/status`，
显示 ASR/TTS 是否已接入，并说明为什么现在不能通话）。

## 四（续）、后端：记忆强度与成本

| 文件 | 内容 |
|---|---|
| `backend/app/memory.py` | `score_memory`：时间衰减（30 天半衰）+ 显著性 + 可信度 + 复述次数 + 相关性 |
| `backend/app/models.py` | `MemoryRecord.recall_count` / `last_recalled_at` |
| `backend/app/migrations.py` | 迁移 `2026102901`，只加列 |
| `backend/app/services.py` | 按当前这句话重排记忆；注入过的记忆 `touch_recall`（复习效应） |
| `backend/app/usage.py`（新） | Token 用量、成本估算、预算余量 |
| `backend/app/routers/health.py` | `GET /api/v1/usage`（需鉴权） |
| `backend/app/config.py` | `context_recent_messages` / `daily_token_budget` / 单价 |

相关性用字符二元组重合度做轻量近似——**不是**真正的向量语义检索，
但对"提到香菜 → 想起她不吃香菜"这种场景够用，且零额外依赖。


| 文件 | 改动 |
|---|---|
| `frontend/LUMI/Views/LUMIStyle.swift` | 新增 `Font` / `Spacing` / `Radius` 令牌 + 气泡最大宽度比例 |
| `frontend/LUMI/Views/MessageBubble.swift` | 正文字体走令牌；内边距 14/10 → 12/9；圆角走令牌 |
| `frontend/LUMI/App/RootView.swift` | Tab 栏改用 `ultraThinMaterial` + `visible` |

关于 Liquid Glass：本机是 Windows，CI 上运行的是 `macos-15` + **Xcode 16.4（iOS 18.5 SDK）**，
该 SDK 里**没有** `glassEffect` / `GlassEffectContainer` / `.buttonStyle(.glass)` 这些符号。
在 Xcode 16 上写它们会直接编译失败，所以本阶段使用的是 `ultraThinMaterial` 这一代系统材质，
并把相关样式收敛到 `LUMIStyle`，等切到 iOS 26 SDK 时只需替换实现，不动调用点。

---

## 五、构建与测试

| 项 | 结果 |
|---|---|
| 后端 pytest | **174 项全部通过**（本机 Windows） |
| Swift 语法检查 | `scripts/swift_lint.py` 通过（91 个类型） |
| iOS 编译 | GitHub Actions `macos-15`，XcodeGen → `xcodebuild test` → 归档 → 打 IPA |
| 产物 | `LUMI-unsigned.ipa`（arm64、未签名），可在 Actions 的 Artifacts 下载 |

> 本轮提交后 CI 仍在排队，最终构建结论以 Actions 页面为准；本文档不预先宣称通过。

---

## 六、明确未完成（不要当成已完成）

| 需求 | 状态 | 说明 |
|---|---|---|
| 微信式聊天交互（长按菜单/引用/图片预览/合并头像） | ✅ 已做 | 引用仅本地展示，不上行给模型 |
| 三套气泡主题 | ✅ 已做 | 共用 `MessageBubble`，只换 `BubbleTheme` |
| 头像/背景自定义 | ✅ 已做 | 未做裁切（只做了等比缩放） |
| App 图标多风格切换 | ❌ 未做 | 需要多套 `.appiconset` + `setAlternateIconName` |
| 原生 Liquid Glass API | ❌ 未做 | 需 Xcode 26 / iOS 26 SDK，当前 CI 为 16.4 |
| DeepSeek 真实接入 | ⚠️ 接口就绪，未接 | 后端是 OpenAI 兼容适配器，填 `LUMI_API_KEY` 即可；**流式输出未做** |
| 记忆检索权重/遗忘曲线 | ✅ 已做 | 衰减+显著性+可信度+复述+相关性；缺真正的向量语义检索 |
| Token 用量与预算 | ✅ 已做 | `/api/v1/usage`；**预算超限时尚未强制拦截请求** |
| Context Builder 分桶预算 | ⚠️ 部分 | 有近期窗口与记忆条数上限，未做按主题压缩与摘要去重 |
| 实时语音通话 / 视频通话 | ❌ 未做 | 需要 WebRTC/LiveKit（涉及第三方服务，未擅自引入） |
| 角色实时渲染（眨眼/口型） | ❌ 未做 | 缺少分层立绘素材；接口未设计 |

---

## 七、下一阶段建议

1. **先确认真机效果**：装新 IPA，确认黑边消失、字号回归正常 —— 这是所有后续 UI 工作的前提。
2. 把 `MessageBubble` 拆成 `BubbleStyle` 参数 + 三个主题预设（只改样式，不复制组件）。
3. 聊天交互补齐：长按菜单（复制/引用/删除）、引用条、图片全屏预览。
4. 头像与背景自定义（PhotosPicker + 简单裁切 + 本地文件存储）。
5. 填 DeepSeek Key → 打通真实回复 → 再做流式（SSE）。
6. 记忆检索加时间衰减与复述加权，并补 Context Builder 的 Token 预算。
