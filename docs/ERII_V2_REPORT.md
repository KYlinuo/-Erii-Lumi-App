# 绘梨衣 AI 陪伴 App — v2.x 重构报告

> 生成时间：2026-10-29 · 分支 `workbuddy-dev`

## 一句话现状

App 已经**只以「绘梨衣」为唯一角色**运行，DeepSeek 已真实接通（不是 Mock），
能流式逐字回复；流量访问的部署方案与脚本已备好，等你提供服务器/域名即可上线。

---

## 一、P0 完成情况

### 1. 去除原本痕迹 ✅（本轮核心）

| 痕迹 | 清理结果 |
|---|---|
| 旧多角色（林穗/祁鹿/沈昼/LUMI） | `personas.py` 只保留 `erii`，`bootstrap` 只播种绘梨衣，`/characters` 前台只返回绘梨衣 |
| Mock Provider 固定话术 | 回复正文早已不再塞「这是 Mock…」；气泡角标从「演示回复·未接入模型」改为克制的「离线」 |
| 默认欢迎语 | 「嗨，我是 LUMI」→「嗯……你来了。今天要待久一点吗？」 |
| 启动页标题 | `LUMI` → `绘梨衣` |
| App 显示名 | `CFBundleDisplayName = 绘梨衣`（上一轮已完成） |
| 后端 title/root | `Project LUMI` → `绘梨衣 AI 陪伴` / `绘梨衣` |
| 系统提示词 | `config.system_prompt` 改为绘梨衣专属 |

**仍然保留、但不暴露给用户**（内部兼容字段）：目录名 `LUMI/`、类名 `LUMIAPIClient` 等
内部标识符——它们只存在于代码里，不在任何用户可见界面出现。改目录名会丢老用户本地数据，故不动。

### 2. 公网 / 流量可访问 ⚠️ 方案就绪，等你提供服务器

- 后端 `main.py` 已启用 `proxy_headers` + `forwarded_allow_ips`，能正确识别 HTTPS 反代。
- 新增 `deploy/`：`Dockerfile`、`Caddyfile`（自动 HTTPS）、`docker-compose.yml`、`README.md`。
- **诚实说明**：真正的公网访问需要你提供一台公网服务器 + 域名。这三样我没有，无法替你完成。
  部署步骤见 `deploy/README.md`，最短 5 条命令。

### 3. DeepSeek 正式接入 ✅（上一轮已完成）

- `LUMI_API_KEY` 已写入 `.env`，`provider=deepseek`、`provider_model=deepseek-flash`（V4.1-Flash-1017）。
- 端到端实测：`is_mock=false`，绘梨衣以真实模型回复，流式逐字正常。
- 模型可修改：`GET/POST /api/v1/model` 运行时切换，默认 `deepseek-flash`。

### 4. 聊天背景全覆盖 / 全面屏适配 ⚠️ 需真机确认

- 黑边根因（`UILaunchScreen` 被 XcodeGen 覆盖）上一轮已修，`CFBundleDisplayName=绘梨衣` 已进包。
- 聊天背景、全面屏、键盘联动的代码已在，但**具体观感必须你装新包在 iPhone 17 Pro 上确认**，
  我没有真机，不能替你下结论。

---

## 二、已完成的功能总览（含之前几轮）

| 能力 | 状态 |
|---|---|
| 唯一人格「绘梨衣」 | ✅ 前台只保留绘梨衣 |
| DeepSeek 真实对话 + 流式 | ✅ 端到端验证 |
| 模型运行时切换 | ✅ `POST /api/v1/model` |
| 长期记忆（分层/来源/可信度/打分/遗忘衰减/复述加权/事实纠正） | ✅ 后端 + 测试 |
| 记忆语义检索 | ✅ `GET /memory?query=` |
| 虚构日记时间线（连贯、关联前文） | ✅ |
| 主动联系（proactive） | ✅ 已有接口，默认关闭 |
| 三套气泡主题 + 背景/头像自定义 | ✅ |
| App 图标切换（4 套绘梨衣图标） | ✅ |
| 语音消息（录音/播放/ASR 接口） | ✅ 录音播放可用，ASR/TTS 待接 |
| 实时通话（LiveKit） | ⚠️ 代码与 token 签发就绪，缺 LiveKit Server + STT/TTS |
| 性能指标 | ✅ `GET /api/v1/metrics` |
| 聊天记录搜索 | ✅ 长按放大镜 + `GET /conversations/{id}/search` |
| 记忆搜索 + 固定 | ✅ 记忆页搜索 + 左滑固定（pinned，不受遗忘衰减） |
| 消息收藏 | ✅ 长按菜单「收藏」+ `star` 接口 |
| 头像裁切 | ✅ ImageCropView 拖动/缩放/圆形框 |
| 数据导出 | ✅ `GET /api/v1/export` 全量导出聊天+记忆 JSON |
| 清除数据 | ✅ `POST /data/wipe`（需 confirm=绘梨衣） |
| 图片理解 | ⚠️ 视觉接口预留（vision.py），DeepSeek 无视觉，默认降级 |
| 语音回复朗读 | ✅ 长按菜单「朗读」（/speech/tts） |
| 应用锁（Face ID） | ✅ 设置→访问认证→应用锁 |
| 快捷表情栏可配置 | ✅ 外观页逗号分隔自定义 |
| 视频影像占位 | ⚠️ 眨眼/呼吸/浮动占位，真实口型需分层立绘 |

---

## 三、编译 / 测试结果

| 项 | 结果 |
|---|---|
| 后端 pytest | **193 项全绿**（本机 Windows） |
| 后端接口实测 | 收藏 200、导出 10 会话 + 11 记忆、真实对话 is_mock=false |
| iOS 构建 | 上一轮 `849fa00` 全绿（含 LiveKit SDK、38 项 XCTest） |
| 本轮 iOS | 前端改动已推送，等 Actions 编译验证 |

---

## 四、已知问题 / 诚实边界

1. **公网未真正上线**：需要你提供服务器 + 域名（见 `deploy/README.md`）。当前用 Cloudflare 临时隧道（地址每次重启会变）。
2. **实时通话未真正跑通**：需要 LiveKit Server（`LUMI_LIVEKIT_URL/KEY/SECRET`）+ STT + TTS 三项凭据。
3. **图片理解未真正接通**：DeepSeek 无视觉，需另配 `LUMI_VISION_MODEL` + `LUMI_VISION_BASE_URL`（OpenAI 兼容视觉模型）。
4. **视频通话动态影像为占位**：当前是立绘 + 呼吸/眨眼/浮动动画；真正口型同步、表情变化需要分层立绘素材（眼睛/嘴巴独立图层），接口已预留。
5. **本轮 iOS 改动未编译验证**：改动需推 CI 后看结果，若失败我会按日志修。
6. **真机观感未确认**：黑边/背景/全面屏/应用锁需你装包实测。
