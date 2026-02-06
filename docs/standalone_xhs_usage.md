# 小红书用户历史笔记批量下载工具

## 简介

`standalone_xhs.py` 是一个用于监控和批量下载指定小红书用户所有历史笔记的独立脚本。

## 功能特点

- ✅ 支持三种笔记获取方式
  - **Playwright 自动化**: 自动打开浏览器，滚动加载所有笔记
  - **文件读取**: 从文本文件读取笔记链接列表
  - **手动输入**: 交互式输入笔记链接
- ✅ 批量下载笔记内容（图片/视频/文案）
- ✅ 智能去重，避免重复下载
- ✅ 下载进度跟踪和统计
- ✅ 可配置下载间隔，避免请求过快
- ✅ 支持断点续传

## 安装依赖

### 基础依赖（必需）

```bash
pip install -r XHS/requirements.txt
```

### Playwright 依赖（可选，使用自动化浏览器时需要）

```bash
pip install playwright
playwright install chromium
```

## 使用方法

### 1. 配置 Cookie

在项目根目录的 `.env` 文件中配置小红书 Cookie：

```env
XHS_COOKIE=your_cookie_here
XHS_USER_AGENT=Mozilla/5.0 ...
```

### 2. 运行脚本

#### 方式一: 手动输入笔记链接（推荐新手）

```bash
python standalone_xhs.py --user-url "用户ID" --method manual
```

然后按提示逐个粘贴笔记链接，输入空行结束。

#### 方式二: 从文件读取笔记链接

1. 创建一个文本文件 `note_links.txt`，每行一个笔记链接：

```text
https://www.xiaohongshu.com/explore/abc123
https://www.xiaohongshu.com/explore/def456
https://www.xiaohongshu.com/explore/ghi789
```

2. 运行脚本：

```bash
python standalone_xhs.py --user-url "用户ID" --method file
```

然后输入文件路径 `note_links.txt`。

#### 方式三: 使用 Playwright 自动获取（需要安装 Playwright）

```bash
python standalone_xhs.py --user-url "https://www.xiaohongshu.com/user/profile/xxx" --method playwright
```

脚本会自动打开浏览器，滚动加载所有笔记并下载。

### 3. 常用参数

```bash
# 限制下载数量（例如只下载前 10 个）
python standalone_xhs.py --user-url "xxx" --max-notes 10

# 设置下载间隔为 5 秒
python standalone_xhs.py --user-url "xxx" --delay 5

# 自定义下载目录
python standalone_xhs.py --user-url "xxx" --download-dir "my_downloads"

# 不跳过已下载的笔记（重新下载）
python standalone_xhs.py --user-url "xxx" --no-skip-existing

# 只下载图片，不下载视频
python standalone_xhs.py --user-url "xxx" --no-video

# 不保存文案
python standalone_xhs.py --user-url "xxx" --no-text
```

### 4. 完整参数说明

```
--user-url USER_URL       用户主页链接或用户ID（必需）
--method {playwright,file,manual}
                          获取笔记列表的方法（默认: manual）
--download-dir DIR        下载目录（默认: downloads/xhs_user）
--delay SECONDS           下载间隔时间/秒（默认: 3.0）
--max-notes N             最大下载笔记数，0表示全部（默认: 0）
--no-skip-existing        不跳过已下载的笔记
--no-text                 不保存文案
--no-image                不下载图片
--no-video                不下载视频
```

## 使用示例

### 示例 1: 快速开始（手动输入）

```bash
python standalone_xhs.py --user-url "xxx" --method manual
```

输出：
```
======================================================================
  手动输入笔记链接
======================================================================
请输入笔记链接，每行一个，输入空行结束:

笔记链接: https://www.xiaohongshu.com/explore/abc123
  ✓ 已添加: abc123
笔记链接: https://www.xiaohongshu.com/explore/def456
  ✓ 已添加: def456
笔记链接: 

[完成] 共添加 2 个笔记

======================================================================
  开始批量下载 (2 个笔记)
======================================================================

[1/2] 下载笔记: 笔记_abc123
  URL: https://www.xiaohongshu.com/explore/abc123
  ✓ 下载成功
  ⏱ 等待 3.0 秒...

[2/2] 下载笔记: 笔记_def456
  URL: https://www.xiaohongshu.com/explore/def456
  ✓ 下载成功

======================================================================
  下载统计
======================================================================
总计: 2
成功: 2
失败: 0
跳过: 0
======================================================================
```

### 示例 2: 从文件批量下载

```bash
# 1. 创建笔记链接文件
echo "https://www.xiaohongshu.com/explore/abc123" > notes.txt
echo "https://www.xiaohongshu.com/explore/def456" >> notes.txt

# 2. 运行下载
python standalone_xhs.py --user-url "xxx" --method file
请输入笔记链接文件路径: notes.txt
```

### 示例 3: 使用 Playwright 自动获取并下载前 5 个笔记

```bash
python standalone_xhs.py \
  --user-url "https://www.xiaohongshu.com/user/profile/xxx" \
  --method playwright \
  --max-notes 5 \
  --delay 2
```

## 下载内容说明

下载的内容会保存在指定的下载目录中，按作者分文件夹存储：

```
downloads/xhs_user/
├── user_xxx_notes.json          # 下载记录（用于断点续传）
└── 作者ID_作者昵称/
    ├── 2024.01.01 12.00_笔记标题.txt    # 文案
    ├── 2024.01.01 12.00_笔记标题_0.jpg  # 图片
    ├── 2024.01.01 12.00_笔记标题_1.jpg
    └── 2024.01.01 12.00_笔记标题.mp4    # 视频
```

## 注意事项

1. **Cookie 配置**: 必须在 `.env` 文件中配置有效的小红书 Cookie，否则可能无法下载内容
2. **下载间隔**: 建议设置合理的下载间隔（3-5秒），避免请求过快被限制
3. **Playwright 使用**: 使用 Playwright 方法需要额外安装依赖，首次使用会自动下载浏览器
4. **断点续传**: 默认启用，避免重复下载。如需重新下载，使用 `--no-skip-existing` 参数

## 常见问题

### Q1: 提示未安装 Playwright？

**A**: 运行以下命令安装：
```bash
pip install playwright
playwright install chromium
```

### Q2: 下载失败怎么办？

**A**: 检查以下几点：
- Cookie 是否有效（可以在浏览器中手动访问笔记链接确认）
- 网络连接是否正常
- 笔记链接是否正确
- 是否需要配置代理

### Q3: 如何获取用户ID？

**A**: 
1. 打开用户主页，URL 格式为 `https://www.xiaohongshu.com/user/profile/用户ID`
2. 直接复制完整 URL 或只复制用户ID部分都可以

### Q4: 下载速度很慢？

**A**: 
1. 可以减少 `--delay` 参数，但不建议低于 2 秒
2. 检查网络连接
3. 如果在国外，可能需要配置代理

## 技术说明

本脚本基于 [XHS-Downloader](https://github.com/JoeanAmier/XHS-Downloader) 项目的 `xhs_downloader.py` 模块开发，复用了其下载功能，并增加了用户历史笔记监控和批量下载能力。

## 开源协议

遵循主项目的 GNU General Public License v3.0 协议。
