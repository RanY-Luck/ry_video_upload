# 小红书笔记批量下载使用指南

本工具用于自动监控和批量下载指定小红书用户的历史笔记（包含视频、图片和文案）。

## ✨ 核心特性

- **安全防封**：采用先进的"API响应拦截"技术，不点击具体链接，避开爬虫检测（无404错误）。
- **完整数据**：自动获取 `xsec_token`，确保能下载高清无水印视频。
- **多种模式**：支持自动抓取、手动输入链接、从文件导入。
- **智能去重**：自动跳过已下载的笔记，支持增量更新。

## 🛠️ 环境准备

1. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

2. **安装浏览器驱动** (首次运行需要)
   ```bash
   pip install playwright
   playwright install chromium
   ```

## 🚀 快速开始

### 方式一：全自动获取（推荐）
只需提供用户主页链接，脚本会自动打开浏览器，滚动页面并捕获数据。

```bash
# 替换为你想要下载的用户主页链接
python standalone_xhs.py --user-url "https://www.xiaohongshu.com/user/profile/5e829xxxxxxxx"
```

### 方式二：指定下载数量
如果你只想下载最近的几篇笔记：

```bash
# 下载最近的 5 篇笔记
python standalone_xhs.py --user-url "用户ID或链接" --max-notes 5
```

### 方式三：手动模式
如果你想自己手动粘贴链接：

```bash
python standalone_xhs.py --user-url "用户ID" --method manual
```

## ⚙️ 高级配置

### 配置文件 (.env)
在项目根目录创建 `.env` 文件（如果不存在），可以配置固定的 Cookie，这样不需要每次扫码登录。

```ini
# .env 文件内容
XHS_COOKIE=你的cookie字符串...
```

### 命令行参数说明

| 参数 | 说明 | 示例 |
|------|------|------|
| `--user-url` | 用户主页链接或用户ID（必需） | `https://...` |
| `--download-dir` | 下载保存目录 | `--download-dir "my_downloads"` |
| `--delay` | 下载间隔时间（秒） | `--delay 5` |
| `--max-notes` | 最大下载数量 (0表示全部) | `--max-notes 10` |
| `--no-video` | 不下载视频 | `--no-video` |
| `--no-image` | 不下载图片 | `--no-image` |
| `--no-skip-existing` | 重新下载已存在的笔记 | `--no-skip-existing` |

## ❓ 常见问题

**Q: 为什么运行后浏览器自动打开了？**
A: 这是正常的。脚本需要通过真实的浏览器访问页面来获取加密的 `xsec_token`。请不要关闭这个窗口，脚本执行完后会自动关闭。

**Q: 为什么提示 "未获取到 xsec_token"？**
A: 脚本会自动尝试多种方法获取。如果 API 拦截失败，会尝试 DOM 分析。如果所有方法都失败（通过 `⚠️` 标记），该笔记可能无法下载高清视频，但脚本仍会尝试基础下载。

**Q: 下载速度太快被限制了怎么办？**
A: 可以增加 `--delay` 参数的值，例如 `--delay 10`（每10秒下载一个）。
