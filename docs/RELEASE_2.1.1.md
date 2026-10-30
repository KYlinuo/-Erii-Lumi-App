# Erii 2.1.1 精简与性能修订

日期：2026-10-30；iOS build 22。基线：用户上传的 Erii-2.1.0-Source-WorkBuddy-5H.zip。本版不改生产数据库结构或记录，不重建 App，不删除既有有效接口。交付源码、可复用 WorkBuddy 技能和约五小时后续任务。

## 已落实的源码修改

| 范围 | 问题与改法 | 验证边界 |
|---|---|---|
| 图片加载 | 旧 MediaStore 全局发布导致多行刷新、气泡内重复图片解码；改为 actor + ImageIO 下采样、单行状态、同键请求复用 | 解码/缓存测试已写，待 XCTest |
| 缓存 | 解码图成本预算 48 MiB、80 项；音频 12 MiB、20 项；内存警告清理 | NSCache 是建议预算，不代表 App 内存硬上限 |
| 图片预览 | 列表默认最长边 960px；打开全屏后按需加载最长边 2560px 的高清版本，加载失败可重试且保留缩略图 | 不宣称无损原图查看，真机待测 |
| 长列表 | 删除 Array(enumerated()) 的临时数组；ChatRows 惰性提供稳定 ID、时间与头像分组；负时间间隔不合并 | 7 个新增 XCTest 覆盖分组、解码、并发等，未执行 |
| 输入与滚动 | 草稿移到独立输入区；图片选择不清空文字草稿；iOS 18+ 仅观测底部布尔变化；合并可取消滚动任务，移除固定延迟 | 键盘与阅读位置需真机回归 |
| 动画 | 去掉未使用的启动脉冲、700ms 人为等待与重复计时；输入中动画随页面/后台/减少动态效果调整；图片缩放尊重减少动态效果 | 未覆盖所有历史页面动画，后续继续审核 |
| 导航与权限 | 聊天补唯一 NavigationStack，设置 sheet/导航复用对应栈；移除全局 Tab 外观覆盖；补 Face ID usage description | 权限描述不等于已验证应用锁安全性 |
| 外观与字体 | 壁纸缩放按像素而非屏幕倍率放大；气泡正文/时间用动态字体样式；移除不必要 JSON sortedKeys | 壁纸解码/压缩后台化仍待做 |
| ProMotion | Info.plist 加 CADisableMinimumFrameDurationOnPhone=true | 允许高刷，不强制固定 120Hz；未采集 FPS |
| 会话列表 | 原逐会话计数和关系加载改为一次 SELECT 返回 DTO；按用户与 character_key 过滤，统计排除软删除消息 | 回归测试确认 20 个会话只发出一次 SELECT，未实例化 Message |
| 后端冗余 | 移除同步无用 max_seq、world 无用查询、proactive 无用最新会话查询、重复 media_id 字段和 7 个闲置导入 | proactive 多会话报错场景新增回归；兼容导出 _tokens_match 保留 |
| 无效界面 | 删除绘梨衣单角色模式下不可达的人格切换 UI 与专用状态、未用实例与占位助手 | 不删除库内旧角色和历史 |
| 交接工具 | 新增源码门禁、Mac 构建/测试脚本；修复 ZIP 无 .git 时自检误报与工作目录依赖 | Linux 缺 Xcode 必须明确失败，不冒充完成 |

## 精简清单与数据

共移除 58 个基线文件，逐项大小、哈希、理由和恢复来源在 `CLEANUP_MANIFEST.json`。主要为旧 IPA、夜间/重复备份、relay 运行队列、演示数据库、过期报告和旧发布脚本；真正被资源目录引用的图片继续保留。

原始 `backend/data/lumi.db` 与输入 ZIP 中的数据库逐字节一致。本次未对真实库运行迁移或服务；测试使用临时数据库。输入包没有真实 .env，未生成新凭据。本包是保留用户数据的私人交接包，公开发布前需另做脱敏导出。

文件减少与 ZIP 缩小主要来自清除旧安装包，不代表 iOS 安装体积、帧率或启动时间已经按同比改善。压缩前后统计在 `PACKAGING_REPORT.json`。

## 实际验证

| 检查 | 本次结果 | 证据 |
|---|---|---|
| 后端完整回归 | 279 passed，62.88 秒 | validation/pytest.txt |
| 后端闲置导入/变量门禁 | Ruff F401/F841 通过 | validation/ruff.txt |
| Swift 静态解析 | 56 文件、140 类型，无阻断；4 条提示已核对为枚举声明/CaseIterable 合成成员 | validation/swift-static.txt |
| Swift 语法解析 | tree-sitter 检查 56 文件，无语法错误；不检查类型或并发隔离 | validation/swift-parser.json |
| 源码结构 | plist 必需键、资产引用、重复字段、生成物门禁通过 | validation/source-audit.json |
| Mac 脚本 | bash 语法通过；Linux 执行返回缺工具状态 | validation/ios-gate.txt |
| Swift/Xcode 编译 | 未执行：当前环境没有 Xcode | 不使用静态解析替代 |
| 新增 7 个 XCTest / 全量 57 个测试方法 | 已保留源码，未执行 | frontend/LUMITests |
| iOS 27.2 真机、自签安装、帧率、内存/能耗 | 未执行 | 见 PERFORMANCE_ACCEPTANCE.md |

本版未调用真实模型、未部署公网、未远程运行桌面 WorkBuddy。静态提示涉及 AppIconChoice.default、AppIconChoice.allCases、BubbleTheme.allCases、NotebookView.Section.allCases；源码有对应枚举 case 或 CaseIterable，最终仍以 Xcode 类型检查为准。

## 剩余限制与后续优先级

1. 在 iOS 27.2 SDK 上编译本版，先处理实际 Swift 6 并发/类型错误；当前静态检查无法证明可安装运行。
2. 冷启动仍有网络等待路径；拆成本地历史优先并防止迟到恢复覆盖新消息，随后做队列与快照持久化优化。
3. MediaStore 待补账户隔离、快速滚动请求背压、共享请求取消策略。当前不同尺寸可能重复下载，内存警告后的在途任务也可能再次填充缓存；不要宣称这一层已经完全优化。
4. 高清预览有像素上限；继续评估原图按需读取/磁盘缓存。外观图片保存仍需后台下采样；长历史 JSON 快照编码需要真实测量。
5. 验证浏览历史时新消息、同步、删除、键盘及图片高度变化；语音播放/录音在后台与退出页面时需完整回归。
6. 把离线仍显示“在线”、朗读失败静默、搜索正文回退定位等体验断点作为下一轮小范围修复；长期 36 项功能不在本轮一次性扩展。
7. 真机记录滚动卡顿、输入延迟、首屏、内存趋势和能耗；不要以 Info.plist 一项配置宣布“完美适配/全局 120 帧”。

执行安排见 `WORKBUDDY_5H_PROMPT.md`。该文档提供约五小时工作量和续跑指令，不承诺 WorkBuddy 单会话运行时长。
