# iOS 27.2 / ProMotion 验收要求

主验收系统为用户的 iOS 27.2；记录实际 iPhone 型号和屏幕最大刷新率。当前环境只有 Linux，以下均是目标或待执行步骤，绝非“已实测 120 帧”。

已加入 Info.plist 的 `CADisableMinimumFrameDurationOnPhone=true`，让支持的系统动画可以使用高于默认值的刷新率。原生控件交给系统节奏控制；不新增全局显示循环。静止、低电量或发热时系统可降频，App 必须正常工作。

具体测试表和性能预算见 `.codebuddy/skills/erii-ios-quality/references/acceptance.md`。统计平均 FPS 不足以验收，需要看卡顿、帧间隔尾部、输入响应和能耗。

## Mac 构建

- 使用包含 iOS 27.2 或更高 SDK 的 Xcode，执行 `xcode-select` 选择实际工具链；保持当前兼容下限 iOS 17，不为了主设备而删除合理降级路径。
- 安装 XcodeGen。在项目根目录执行 `bash scripts/ios_validate.sh`。脚本先检查 SDK，之后用 Release 配置编译真机目标，使用无签名构建验证源码。
- 设置 `ERII_TEST_DESTINATION='platform=iOS Simulator,id=实际模拟器UDID'` 后执行脚本，运行 XCTest。未设置时脚本返回 3，代表只构建、未完成测试；缺工具返回 2。
- 再用用户自己的签名方案安装到真机。未签名构建、模拟器、语法检查都不能证明 iOS 27.2 上的帧率。
- 现有 GitHub workflow 的 runner 不保证提供目标 SDK。要记录实际版本，不能因为 workflow 绿了就标 iOS 27.2 适配完成。

## 需要继续验证的路径

1. 输入法中文拼音候选、长按编辑、滑动撤键盘、引用、连发；保证手势跟手，不能清空未发送草稿。
2. 快速浏览历史时收到回复/同步/删除，阅读位置不跳；回底提示数量准确，重复调度可取消。
3. 图片滚动首显、失败重试、缓存淘汰、旋转照片方向、透明 PNG；列表最长边 960px，全屏按需加载最长边 2560px 高清图；继续验证取消、错误回退和无损原图需求。
4. 后台恢复、录音/播放结束、低电量和系统减少动态效果；CPU 不应在静止页面保持高频唤醒。
5. 网络慢/断线不阻塞本地阅读、草稿与滚动；冷启动本地历史仍应继续优化到网络探测之前。
6. 原生 Tab/导航在新 SDK 下的系统材质与安全区，字体放大和 VoiceOver；勿用重复的模糊和多层阴影覆盖系统导航。

## 官方参考

- https://developer.apple.com/documentation/quartzcore/optimizing-iphone-and-ipad-apps-to-support-promotion-displays
- https://developer.apple.com/documentation/bundleresources/information-property-list/cadisableminimumframedurationonphone
- https://developer.apple.com/documentation/swiftui/view/onscrollgeometrychange(for:of:action:)
- https://developer.apple.com/documentation/technologyoverviews/adopting-liquid-glass
- https://developer.apple.com/news/releases/?id=10262026b

查询日期：2026-10-30。运行时刷新率由系统最终决定，不能从配置键推导帧率成绩。
