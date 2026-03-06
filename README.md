# 🎥 自动化短视频搬运/采集/发布工具 (Ry Video Upload)

这是一个全自动化的短视频采集、去重和发布工具。它能够定时从抖音等平台采集视频，经过智能去重处理后，自动发布到微信视频号，并利用 AI 生成爆款标题和标签。

## ✨ 主要功能

*   **⚡ 全自动采集**: 集成 `f2` 工具，支持定时从抖音指定用户主页采集最新视频。
*   **🤖 智能去重**: 
    - 使用 FFmpeg 进行深度处理。
    - 支持去除/添加水印（文本、图片）。
    - 智能静音检测与消除。
    - 自动添加背景音乐。
    - 视频镜像、旋转、裁剪、加速/减速。
    - 如果有字幕，支持使用 Whisper 重新生成字幕（繁转简）。
    - 画面特效：高斯模糊、边框模糊、画中画等。
*   **🚀 自动发布**: 
    - 对接微信视频号上传接口。
    - 集成阿里云 Qwen-VL (DashScope) 大模型，自动根据视频内容生成吸引人的标题和标签。
*   **📅 任务调度**: 内置 APScheduler，支持全自动定时运行，自动处理 403 Forbidden 问题（通过刷新设备 ID）。
*   **🛠️ 独立工具**: 提供独立的去重和上传脚本，方便单独使用。

## 📂 目录结构

```
ry_video_upload/
├── Dedup/                  # 视频去重模块
│   ├── dedup.py            # 去重核心逻辑
│   └── logs/               # 去重日志
├── Download/               # 视频下载目录
│   └── douyin/post/        # 抖音视频默认存储路径
├── Upload/                 # 视频上传模块
│   ├── videos/             # 待上传视频目录(去重后的输出目录)
│   ├── vx_upload.py        # 视频号上传脚本
│   ├── utils/              # 工具类 (配置加载等)
│   └── cookies/            # 上传账号 Cookie
├── logs/                   # 全局应用日志
├── main.py                 # 主程序入口 (调度器)
├── standalone_dedup.py     # 独立去重工具
├── standalone_upload.py    # 独立上传工具
├── flush_device_id.py      # 设备ID刷新脚本 (解决 F2 403错误)
├── setup_config.py         # 配置初始化工具
├── my_apps.yaml            # F2 采集工具配置
├── requirements.txt        # 项目依赖
└── .env                    # 环境变量配置
```

## ⚙️ 环境要求

*   **Operating System**: Windows (推荐) / Linux
*   **Python**: 3.10+
*   **FFmpeg**: 必须安装并添加到系统 PATH，或者放置在默认搜索路径 (`C:\ffmpeg\bin` 等)。
*   **Node.js**: (可选) 部分依赖可能需要。

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/your-repo/ry_video_upload.git
cd ry_video_upload
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置文件

#### 3.1 环境变量 (.env)

复制示例文件并填入你的配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```ini
# 阿里云 DashScope API Key (用于 AI 生成标题/标签) 必须配置
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 抖音目标用户主页链接 (必须配置)
DOUYIN_TARGET_URL=https://www.douyin.com/user/xxxxxxxxxxxx

# 调度间隔 (分钟)
SCHEDULE_INTERVAL=300

# 时区
TIMEZONE=Asia/Shanghai
```

#### 3.2 采集配置 (my_apps.yaml)

该文件用于配置 `f2` 采集工具。通常不需要修改，除非你需要更改采集模式或添加代理。

#### 3.3 账号 Cookie

*   **视频号上传**: 将你的微信视频号 Cookie 信息放入 `Upload/cookies/tencent_uploader/account.json`。

### 4. 运行程序

#### 🟢 启动全自动主程序

主程序会根据 `SCHEDULE_INTERVAL` 定时执行采集 -> 去重 -> 上传的完整流程。

```bash
python main.py
```

#### 🟡 仅运行去重

扫描 `Download` 目录下的所有视频，进行去重处理并输出到 `Upload/videos`。

```bash
python standalone_dedup.py
```

#### 🔵 仅运行上传

将 `Upload/videos` 目录下的视频上传到视频号。

```bash
python Upload/vx_upload.py
```

#### 🔵 检测到用户主页URL，自动使用 Playwright 获取笔记列表

```bash
python standalone_xhs.py --user-url "https://www.xiaohongshu.com/user/profile/5e8297920000000001001c90" --max-notes 5
```

---

## 📕 小红书监控与上传模块

本项目内置了两个专为小红书设计的独立工具，可单独使用，也可配合形成「监控 → 下载 → AI 润色 → 自动上传」的完整流水线。

```
xhs_monitor.py   ←  实时监控博主新帖，自动下载图文/视频
       ↓
downloads/xhs_monitor/{作者}/{note_id}_{标题}/
       ↓
xhs_upload.py    ←  扫描下载目录，AI 润色文案，自动发布到创作者中心
```

---

### 🔍 xhs_monitor.py — 博主新帖实时监控

#### 功能概述

- 持续轮询指定小红书博主的主页，检测是否有新笔记发布
- 首次运行时仅建立基线（记录当前所有笔记 ID），不执行下载，从第二轮起才下载真正的"新帖"
- 优先通过官方接口获取**高清无水印**原图/原生视频，失败时自动降级为 DOM 抓取
- 下载内容包括：图片、视频、文案（保存为 `.txt`）
- 支持同时监控多个博主（逗号分隔）
- 通过 Bark 向 iPhone 推送新帖通知
- 登录状态自动持久化（`XHS_STORAGE_STATE`），下次启动无需重新扫码

#### 目录输出结构

```
downloads/xhs_monitor/
├── .seen/
│   └── {user_id}_seen.json     # 已知笔记 ID 记录（防重复下载）
└── {作者昵称}/
    └── {note_id}_{标题}/
        ├── {标题}.txt           # 文案（标题 / 作者 / ID / URL / 正文）
        ├── {标题}_0.jpg         # 图文笔记图片（多图依次编号）
        └── {标题}_0.mp4         # 视频笔记视频
```

#### .env 配置项

| 变量名 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `XHS_COOKIE` | 否 | — | 小红书 Cookie 字符串（有持久化登录态时可不填）|
| `XHS_MONITOR_USERS` | **是** | — | 博主主页 URL，多个用英文逗号分隔 |
| `XHS_MONITOR_INTERVAL` | 否 | `600` | 轮询间隔（秒），建议不低于 300 |
| `XHS_MONITOR_DIR` | 否 | `downloads/xhs_monitor` | 下载根目录 |
| `XHS_STORAGE_STATE` | 否 | `downloads/.xhs_storage_state.json` | 登录态持久化文件路径（监控和上传共享）|
| `BARK_KEY` | 否 | — | Bark 推送 Key（不填则不推送）|
| `BARK_SERVER` | 否 | — | Bark 服务器地址（默认官方服务）|

`.env` 示例：

```ini
XHS_MONITOR_USERS=https://www.xiaohongshu.com/user/profile/5e8297920000000001001c90,https://www.xiaohongshu.com/user/profile/另一个ID
XHS_MONITOR_INTERVAL=600
XHS_MONITOR_DIR=downloads/xhs_monitor
BARK_KEY=your_bark_key_here
BARK_SERVER=https://api.day.app
```

#### 启动命令

```bash
# 使用 .env 中的博主列表，持续监控
python xhs_monitor.py

# 手动指定单个博主
python xhs_monitor.py --users "https://www.xiaohongshu.com/user/profile/xxx"

# 监控多个博主（逗号分隔）
python xhs_monitor.py --users "url1,url2,url3"

# 每 5 分钟检查一次
python xhs_monitor.py --interval 300

# 仅检查一次后退出
python xhs_monitor.py --once

# 指定下载目录
python xhs_monitor.py --download-dir "D:/小红书下载"
```

#### 工作流程详解

```
启动
 ├─ 读取 .env / 命令行参数，初始化博主监控器列表
 ├─ 加载持久化登录态（storage_state.json）
 └─ 进入轮询循环
      ├─ 启动 Chromium（headless=False，反检测模式）
      ├─ 访问博主主页，等待 15 秒渲染 + 滚动 3 次加载更多
      ├─ 从 DOM 提取笔记 ID 列表
      │    └─ 若为空 → 等待 60 秒让用户手动完成验证码/登录
      ├─ 对比已知 ID，找出新笔记
      │    └─ 首次运行 → 仅建立基线，不下载
      ├─ 逐篇处理新笔记
      │    ├─ 点击笔记卡片，导航到详情页
      │    ├─ 调用官方 API 获取高清媒体直链（失败则降级 DOM 抓取）
      │    ├─ 下载图片/视频，保存文案 .txt
      │    └─ 推送 Bark 通知
      ├─ 保存登录态（storage_state）
      ├─ 更新已知 ID 记录文件
      └─ 等待 interval 秒后开始下一轮
```

---

### 📤 xhs_upload.py — 图文/视频笔记批量上传

#### 功能概述

- 扫描 `xhs_monitor` 的下载输出目录，找出所有尚未上传的笔记文件夹
- 自动识别笔记类型：含 `.mp4` 文件 → 视频笔记，仅含图片 → 图文笔记
- 调用**阿里云百炼 qwen 模型**对标题和正文进行 AI 润色二创（失败时安全降级，使用原始文案）
- 使用 Playwright 模拟浏览器，在 `creator.xiaohongshu.com` 完成发布
- 维护上传历史记录（`logs/xhs_upload_history.txt`），避免重复上传
- 发布成功后通过 Bark 推送通知
- 支持 `--dry-run` 只扫描不上传，方便调试

#### .env 配置项

| 变量名 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `XHS_STORAGE_STATE` | 否 | `downloads/.xhs_storage_state.json` | 共享登录态文件（与监控脚本复用）|
| `XHS_UPLOAD_ACCOUNT` | 否 | — | 专用上传账号 Cookie JSON 路径（优先级高于共享登录态）|
| `XHS_COOKIE` | 否 | — | Cookie 字符串（无 JSON 文件时使用）|
| `XHS_UPLOAD_DIR` | 否 | `downloads/xhs_monitor` | 扫描的下载目录 |
| `XHS_UPLOAD_INTERVAL` | 否 | `300` | 持续循环模式的轮询间隔（秒）|
| `DASHSCOPE_API_KEY` | 否 | — | 阿里云百炼 API Key，用于 AI 润色（不填则跳过润色）|
| `AI_MODEL` | 否 | — | 使用的模型名，如 `qwen-turbo`（不填则由 SDK 默认）|
| `BARK_KEY` | 否 | — | Bark 推送 Key |
| `BARK_SERVER` | 否 | — | Bark 服务器地址 |

`.env` 示例：

```ini
XHS_UPLOAD_ACCOUNT=Upload/cookies/xhs_upload_account.json
XHS_UPLOAD_DIR=downloads/xhs_monitor
XHS_UPLOAD_INTERVAL=300
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
AI_MODEL=qwen-turbo
BARK_KEY=your_bark_key_here
BARK_SERVER=https://api.day.app
```

#### 启动命令

```bash
# 持续循环模式（默认，每 300 秒扫描一次）
python xhs_upload.py

# 单次运行后退出
python xhs_upload.py --once

# 试运行：只扫描打印，不实际上传
python xhs_upload.py --dry-run

# 指定扫描目录
python xhs_upload.py --dir downloads/xhs_monitor

# 指定轮询间隔（秒）
python xhs_upload.py --interval 600

# 指定 Cookie 字符串（覆盖 .env）
python xhs_upload.py --cookie "a1=xxx;web_session=yyy"

# 指定账号 Cookie JSON 文件
python xhs_upload.py --account Upload/cookies/xhs_upload_account.json
```

#### 工作流程详解

```
启动
 ├─ 加载 .env，初始化上传历史记录
 └─ 进入轮询循环
      ├─ 扫描 {XHS_UPLOAD_DIR}/{作者}/{note_id}_{标题}/ 目录
      │    ├─ 读取 .txt 文案（标题 / 正文）
      │    ├─ 识别图片文件列表 / 视频文件列表
      │    └─ 过滤已上传（对比 history.txt）
      ├─ [AI 润色] 调用阿里百炼对标题/正文润色（最多重试 3 次，失败降级）
      ├─ 启动 Chromium（headless=False，注入反检测脚本）
      ├─ 检查登录状态
      │    ├─ 有效 → 直接继续
      │    └─ 无效 → 等待用户扫码（最多 120 秒），成功后保存登录态
      └─ 逐篇上传
           ├─ 打开发布页，切换图文/视频 Tab
           ├─ 上传媒体文件（set_input_files）
           ├─ 等待编辑区渲染后填写标题（≤20字）
           ├─ 填写正文（ProseMirror 富文本，自动处理 #话题 标签）
           ├─ 轮询发布按钮状态（最多等待 300 秒，适配大视频上传）
           ├─ 点击发布，确认成功
           ├─ 写入 history.txt，推送 Bark 通知
           └─ 等待 30 秒后上传下一篇（防风控）
```

#### AI 润色说明

上传前会自动调用阿里云百炼对文案进行润色，提升互动率。要启用此功能，需：

1. 在 [阿里云百炼控制台](https://bailian.console.aliyun.com/) 申请 API Key
2. 在 `.env` 中设置 `DASHSCOPE_API_KEY` 和 `AI_MODEL`（如 `qwen-turbo`）
3. 安装 SDK：`pip install dashscope`

润色策略：
- 标题：控制在 20 字以内，加入情感钩子，添加 1-2 个 emoji
- 正文：保留核心信息，语气更亲切，自动补充 3-5 个话题标签
- 任何异常（网络/API 错误）均安全降级，使用原始文案继续上传，**不会中断流程**

#### 登录方式说明

上传脚本支持三种登录方式，按优先级排序：

| 优先级 | 方式 | 配置项 | 说明 |
|---|---|---|---|
| 1 | 专用账号 JSON | `XHS_UPLOAD_ACCOUNT` | Playwright `storage_state` 格式，首次扫码后自动保存 |
| 2 | 共享登录态 | `XHS_STORAGE_STATE` | 与 `xhs_monitor.py` 共用同一个登录态文件 |
| 3 | Cookie 字符串 | `XHS_COOKIE` | 从浏览器 DevTools 手动复制 |

> **推荐方式**：首次运行时让浏览器弹出扫码界面，扫码成功后登录态会自动保存到 `XHS_UPLOAD_ACCOUNT` 指定路径，后续无需重复扫码。

#### 日志与调试截图

| 文件路径 | 说明 |
|---|---|
| `logs/xhs_upload.log` | 上传详细日志 |
| `logs/xhs_monitor.log` | 监控详细日志 |
| `logs/xhs_upload_history.txt` | 已上传笔记 ID 记录 |
| `logs/xhs_upload_debug_*.png` | 自动保存的调试截图（上传异常时触发）|

---

### 🔗 监控 + 上传联动示例

推荐同时启动两个脚本，监控脚本负责持续下载，上传脚本负责定时发布：

```bash
# 终端 1：启动博主监控（每 10 分钟检查一次）
python xhs_monitor.py

# 终端 2：启动自动上传（每 5 分钟扫描一次下载目录）
python xhs_upload.py --interval 300
```

或使用 `--once` 配合外部定时任务（如 Windows 任务计划、cron）按需触发：

```bash
# 只运行一轮
python xhs_monitor.py --once
python xhs_upload.py --once
```

---

## 🛠️ 常见问题

**Q: 采集时出现 403 Forbidden 错误？**
A: 主程序会自动检测此错误并调用 `flush_device_id.py` 刷新设备 ID，然后重试。你也可以手动运行 `python flush_device_id.py`。

**Q: 视频处理失败，提示 Logs 目录不存在？**
A: 最新版本已修复此问题，程序会自动创建所需的日志目录。

**Q: 如何修改去重参数（如水印、背景音乐）？**
A: 修改 `Dedup/dedup.py` 中的 `VideoConfig` 类默认参数，或者直接替换 `Dedup/assets` 目录下的素材（如 `watermark.png`, `bgm.mp3`）。

**Q: xhs_monitor.py 启动后什么都没下载？**
A: 这是正常行为。首次运行只建立基线（记录当前所有笔记 ID），不执行下载。等博主发布新帖后，下一轮检查时才会下载。

**Q: xhs_upload.py 提示"未找到可用发布按钮"？**
A: 通常是媒体文件仍在上传中（大视频文件尤其明显）。脚本已内置最多等待 300 秒的轮询机制。如果超时，请检查 `logs/xhs_upload_debug_*.png` 截图排查页面状态。

**Q: 如何只监控不上传，或只上传不监控？**
A: 两个脚本完全独立，可以单独运行。`xhs_monitor.py` 负责下载，`xhs_upload.py` 负责上传，只需运行其中一个即可。

**Q: AI 润色没有生效？**
A: 检查 `.env` 中是否正确配置了 `DASHSCOPE_API_KEY` 和 `AI_MODEL`，并确认已安装 `dashscope` 包（`pip install dashscope`）。润色失败时日志中会有 `[AI润色] ⚠️` 警告，不影响上传。

## 📝 许可证

MIT License
