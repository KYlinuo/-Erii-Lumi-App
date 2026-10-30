# Erii 2.1.1 架构入口

更新于 2026-10-30。iOS 使用 SwiftUI，后端使用 FastAPI / SQLAlchemy / SQLite，Windows 桥接通过同一服务端接口同步。服务端管理会话、记忆和虚构事件；客户端保留本地消息快照、发送状态和连接设置。

| 层 | 主要入口 | 约束 |
|---|---|---|
| iOS 交互 | RootView、ChatView、NotebookView、MeView | 三个主入口；各页面避免重复导航栈；网络等待不应阻塞输入和滚动 |
| iOS 状态 | AppSession、ChatViewModel、MessageStore | 请求 ID 重试复用；恢复和同步必须防止覆盖刚产生的状态 |
| 媒体渲染 | MediaStore、MessageImageView、ImagePreviewView | actor 下采样、按尺寸缓存、每行独立状态；预览按需加载 |
| 后端路由 | backend/app/routers | 验证令牌、限流，返回可区分的能力与错误状态 |
| 聊天编排 | services.py、llm/ | 幂等、消息落库、上下文、模型生成；测试使用桩服务 |
| 记忆与陪伴 | memory.py、world.py、companion.py、activities.py | 用户事实与虚构内容区分来源；临时聊天保持隔离 |
| 数据层 | models.py、migrations.py | 在副本测试升级与恢复；真实运行库使用 SQLite 一致备份 |

绘梨衣是当前默认角色；历史角色记录继续保留。清理不可达选择界面不意味着删除旧关系、会话或迁移。后端模型和迁移是当前表结构的依据，旧架构文档中的固定表数量与早期测试数字不再适用。

同步分页依赖 conv_seq，删除使用 tombstone；分页游标与删除在已同步设备上的传播仍需持续回归。备份恢复有预览、校验和事务保护，不能把简单复制运行中的 .db 当作一致备份。

本次只优化确定的热点，没有迁移全部前端状态架构。长聊天 JSON 持久化、媒体账户隔离、请求背压、本地优先启动是后续任务。性能目标与实际成绩分开记录，见 [版本报告](docs/RELEASE_2.1.1.md) 和 [验收要求](docs/PERFORMANCE_ACCEPTANCE.md)。

详细接口以路由代码和运行时 OpenAPI 为准；docs/API.md 与 docs/ARCHITECTURE.md 保留早期设计背景，不是最新完成证明。
