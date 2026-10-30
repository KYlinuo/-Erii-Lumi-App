# 本轮交接记录 · 2026-10-30（续 2.1.1）

基线 Erii 2.1.1 / build 22 → 本轮「聊天连续性」审查与精简。未改数据库结构、未删用户数据、未重建项目；后端测试从 279 增至 283，全部通过。

## 本轮实际完成（均有可验证证据）

1. **引用消息进入模型上下文（确定性缺口修复）**
   - 后端：`ChatRequest` 新增 `quoted_text`；`services._wrap_user_message` 把「<引用>…</引用>」与「<用户现在说>…</用户现在说>」分隔注入模型上下文；落库正文仍是原始新内容；长期记忆抽取继续只吃 `user_text`（引用不进记忆）。
   - 前端：`ChatRequest.quotedText` / `sendMessage(quotedText:)` / `sendMessageStream(quotedText:)`；`ChatViewModel` 用 `quoteForContext` 存全文并在发送时上行。
   - 测试：新增 `tests/test_quote_context.py`（4 项），覆盖进入上下文、不落库正文、不进记忆、幂等重放一致。

2. **图片跨尺寸下载复用 + 换服/登出清缓存（MediaStore）**
   - `MediaStore` 增加 `rawData` 原始字节缓存（按「资源」不含尺寸），列表 960px 与全屏 2560px 共用同一次下载；`images` 仍按「资源+尺寸」缓存解码结果；同资源并发请求合并。
   - `SettingsViewModel`：换服务器（baseURL 变化）与清令牌（登出）时清媒体缓存。

3. **冷启动本地历史优先（AppSession.bootstrap）**
   - 重排为：先 `restoreHistory()`（本地）→ 立即进入聊天 → 再做健康探测 / 增量同步 / 主动消息；网络不再阻塞首屏。

4. **搜索定位不按正文误滚**
   - `ChatView.scrollToMessage`：优先服务端 ID 精确定位；本地窗口无该 ID 时仅在正文唯一匹配时才回退，避免滚到重复文本的另一条。

## 验证证据（本机 Windows，无 Xcode）

| 检查 | 结果 | 说明 |
|---|---|---|
| 后端全量回归 | **283 passed**（47s） | 新增 4 项引用上下文测试 |
| Ruff F401/F841 | 通过 | 无新增闲置导入 |
| audit_source.py | passed | 源码结构门禁 |
| swift_lint.py | 无阻断 | 仍为 4 条已知误报（枚举 CaseIterable 合成成员） |
| Xcode 编译 / XCTest / 真机 | **未执行** | 无 macOS/Xcode，前端改动仅静态校验 |

## 剩余限制（未变，供下一轮）

- iOS 27.2 真机编译与 ProMotion 帧率/能耗仍未采集（见 PERFORMANCE_ACCEPTANCE.md）。
- MediaStore 仍缺「快速滚动的在途请求背压与取消」（当前靠 NSCache 上限 + 内存警告清理）；内存警告后的在途下载仍可能回填缓存。
- 长历史 JSON 单快照 `messages.json` 的 10000 条编码开销未在真机实测；未做分片/SQLite 重构（避免为少量记录提前复杂化）。
- 冷启动历史恢复已前置，但「迟到恢复覆盖草稿/新消息」的竞态仍需真机多轮验证。
- 离线「在线」状态、朗读失败提示、搜索跨窗口加载并高亮等体验断点仍未闭环。

## 下一步（建议顺序）

1. 有 Mac 时先跑 `scripts/ios_validate.sh` 做目标 SDK 编译 + XCTest，处理真实 Swift 6 类型/并发错误。
2. 真机采集：快速滚动 hitch、输入回显 P95、首屏、内存/能耗、低电量/减少动态效果。
3. MediaStore 补背压/取消与账户隔离；测长历史快照开销后再决定分片。
