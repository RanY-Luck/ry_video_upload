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

## 🛠️ 常见问题

**Q: 采集时出现 403 Forbidden 错误？**
A: 主程序会自动检测此错误并调用 `flush_device_id.py` 刷新设备 ID，然后重试。你也可以手动运行 `python flush_device_id.py`。

**Q: 视频处理失败，提示 Logs 目录不存在？**
A: 最新版本已修复此问题，程序会自动创建所需的日志目录。

**Q: 如何修改去重参数（如水印、背景音乐）？**
A: 修改 `Dedup/dedup.py` 中的 `VideoConfig` 类默认参数，或者直接替换 `Dedup/assets` 目录下的素材（如 `watermark.png`, `bgm.mp3`）。

## 📝 许可证

MIT License
