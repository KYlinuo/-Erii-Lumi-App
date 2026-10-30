# Erii 2.1.1 接手入口

日期：2026-10-30。优先阅读 RELEASE_2.1.1.md、PERFORMANCE_ACCEPTANCE.md 和 WORKBUDDY_5H_PROMPT.md。不要再沿用旧版文档中的 CI 成绩、过期 IPA、夜间备份路径或含凭据的 Git URL 推送方式。

## 启动顺序

1. 在新的目录解压源码，保留本机现有更改。核对 backend/app/__init__.py 与 frontend/project.yml 的 2.1.1 / build 22。
2. 这是私人交接包，原始数据库保留，.env 未随包提供。恢复自己的后端配置；先做一致备份，再对副本测试。不要把旧运行数据当缓存删掉。
3. 按根 README 安装开发依赖，运行源码门禁、Ruff、pytest 和 Swift 静态脚本。测试依赖与真实模型配置分开。
4. 在 Mac 上优先执行 scripts/ios_validate.sh，确认实际 iOS SDK。测试目标必须显式指定；签名和真机验收独立记录。
5. 导入 erii-ios-quality 技能，或直接读取 .codebuddy/skills/erii-ios-quality/SKILL.md，然后按五小时提示词推进。

## 当前最重要的下一步

- 修实际编译错误，再做本地历史先显示、持久化发送队列和迟到结果保护。
- 为媒体加载补账户隔离、背压、取消与尺寸稳定，测长列表和大量图片。
- iOS 27.2 真机测键盘、页面返回、滚动位置、系统材质、减少动态效果和高刷。
- 只选两三项小功能闭环，优先草稿恢复、错误可见、准确搜索与状态可信；暂不扩展新主导航。

## 不能误认的结果

- 279 项 pytest 通过只证明当前后端回归；57 个 XCTest 方法尚未在本轮运行。
- 56 个 Swift 文件的静态检查不等于编译或真机流畅。
- ProMotion opt-in 不等于 120fps 锁帧；静止、低电量、温控降频应正常工作。
- 本包不含新 IPA，没有执行桌面签名或公网部署。

阶段进展写入 docs/WORK_LOG.md，记录改动、真实证据、阻塞与下一步。交付时更新 release 和源码包，不把旧文件改名当新成果。
