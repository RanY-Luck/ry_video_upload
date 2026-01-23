# 视频搬运工具 - 抖音全自动视频采集、去重与发布

**一款强大的全自动化内容创作流水线工具，专为抖音视频采集、二次创作和多平台发布设计。**

> **📢 重要更新**: 本项目已从 TikTok 改为抖音采集，适配国内用户使用！

## ✨ 核心功能

### 📥 自动下载 (Auto-Download)
- **实时监控**: 7x24 小时自动监听指定抖音博主的发布状态
- **即时下载**: 一旦发布新视频，立即无水印下载到本地

### ✂️ 智能去重 (Intelligent Deduplication)
- 提供一套强大的视频二次创作工具箱
- **🚀 GPU 加速**: 利用 NVIDIA 显卡大幅提升处理速度
- **内容增强**: 自动字幕、自定义标题、背景音乐、画中画
- **视频处理**: 静音剪辑、镜像、旋转、裁剪、淡入淡出
- **高级特效**: 背景模糊、帧交换、颜色偏移、频域扰乱等

### 🚀 AI 驱动上传 (AI-Powered Upload)
- **AI 标题生成**: 调用阿里云百炼 AI 大模型，自动生成爆款标题
- **自动化发布**: 模拟浏览器操作，自动填写信息并发布视频

## 🚀 快速开始

### 系统要求

1. **操作系统**: Windows
2. **必需软件**:
   - Python 3.12+
   - Node.js 22.x
   - FFmpeg
   - Chrome 浏览器

### 安装步骤

#### 1. 克隆仓库
```bash
git clone https://github.com/RanY-Luck/ry_video_upload.git
cd ry_video_upload
```

#### 2. 安装依赖
```bash
setup.bat
```

#### 3. 环境配置

**创建 .env 配置文件**

**方式一: 使用配置向导 (推荐)**
```bash
python setup_config.py
```

**方式二: 手动配置**
```bash
# 复制示例配置
copy .env.example .env
```

**编辑 `.env`** 文件并填写以下必需配置:

```bash
# 抖音目标用户 URL (必填)
DOUYIN_TARGET_URL=https://www.douyin.com/user/YOUR_TARGET_USER_ID

# 阿里云百炼 API Key (必填)
DASHSCOPE_API_KEY=YOUR_DASHSCOPE_API_KEY

# 调度间隔 (分钟，建议 5-60)
SCHEDULE_INTERVAL=300
```

**获取阿里云百炼 API Key**:
1. 访问 [阿里云百炼控制台](https://bailian.console.aliyun.com/)
2. 注册并创建 API Key
3. 复制 API Key 到 `.env` 文件中

#### 4. 配置抖音采集

**方式一: 自动配置 (推荐)**
```bash
setup_douyin.bat
```

**方式二: 手动配置**

**步骤 1**: 获取抖音 Cookie
- 访问 https://www.douyin.com/ 并登录
- 按 F12 打开开发者工具 → Network → 刷新页面
- 复制任意请求的 Cookie 值
- 粘贴到 `my_apps.yaml` 的 `douyin.cookie` 字段

**步骤 2**: 测试 Cookie
```bash
python test_douyin_cookie.py
```

**步骤 3**: 刷新设备 ID
```bash
python flush_device_id.py
```

**步骤 4**: 修改目标用户
- 编辑 `config.yaml` 中的 `douyin.target_user_url`
- 填入要采集的抖音用户主页 URL

**步骤 5**: 测试采集
```bash
f2 dy -c my_apps.yaml -u https://www.douyin.com/user/你的目标用户ID -m post
```

#### 5. 启动自动调度

**完整流程 (下载 + 去重 + 上传)**
```bash
start.bat
# 或
python main.py
```

**独立运行去重**
```bash
run_dedup.bat
# 或
python standalone_dedup.py
```

**独立运行上传**
```bash
run_upload.bat
# 或
python standalone_upload.py
```

## 📖 配置说明

### 配置文件结构

项目使用两个配置文件:

1. **`.env`** - 环境变量配置文件 (敏感信息)
   - 抖音目标用户 URL
   - AI API Key
   - 调度配置
   - 上传配置

2. **`my_apps.yaml`** - F2 框架配置文件
   - 抖音 Cookie
   - 请求头配置
   - 代理设置

### 主要配置项

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `DOUYIN_TARGET_URL` | 抖音目标用户 URL | 必填 |
| `DASHSCOPE_API_KEY` | 阿里云百炼 API Key | 必填 |
| `SCHEDULE_INTERVAL` | 调度间隔 (分钟) | 300 |
| `TIMEZONE` | 时区 | Asia/Shanghai |
| `VIDEO_CATEGORY` | 视频分类 | CUTE_PETS |
| `DELETE_AFTER_UPLOAD` | 上传后删除本地视频 | false |

完整配置说明请参考 `.env.example`。

## ⚠️ 重要提示

### Cookie 管理
- 抖音 Cookie 有效期通常为几天到几周
- Cookie 过期后需要重新获取并更新 `my_apps.yaml`
- 建议准备多个账号的 Cookie 轮换使用

### 采集频率
- 默认设置为 300 分钟 (5 小时) 采集一次
- 不建议设置过于频繁，避免被检测为爬虫
- 可在 `config.yaml` 中调整 `scheduler.interval_minutes` 参数

### 代理设置
- 抖音在国内可直接访问，无需代理
- 配置文件中的 `proxies` 保持空即可

### 配置文件安全
- **切勿将 `config.yaml` 提交到 Git**
- 该文件已添加到 `.gitignore`
- 使用 `config.yaml.example` 作为模板

## 🔍 常见问题

### 1. 响应内容为空
**原因**: Cookie 失效或被检测  
**解决**: 重新获取 Cookie，运行 `python flush_device_id.py`

### 2. 找不到用户
**原因**: 用户 URL 格式错误  
**解决**: 确保 URL 包含完整的 `sec_user_id`

### 3. 下载失败
**原因**: 网络问题或视频已删除  
**解决**: 检查网络连接，确认视频是否存在

### 4. AI 生成标题失败
**原因**: API Key 无效或配额不足  
**解决**: 检查 `.env` 中的 `DASHSCOPE_API_KEY` 是否正确

### 5. 配置文件加载失败
**原因**: `.env` 不存在或格式错误  
**解决**: 
```bash
# 使用配置向导
python setup_config.py

# 或手动创建
copy .env.example .env

# 测试配置加载
python config_loader.py
```

## 📂 目录结构

```
video-mover/
├── Download/douyin/post/    # 下载的原始视频
├── Dedup/                   # 去重脚本
├── Upload/                  # 上传脚本和配置
│   ├── videos/             # 去重后待上传的视频
│   └── cookies/            # 账号配置
├── logs/                    # 日志文件
├── .env                    # 环境变量配置文件 (需自行创建)
├── .env.example            # 配置文件示例
├── config_loader.py        # 配置加载器
├── my_apps.yaml            # F2 框架配置
├── main.py                 # 主程序 (完整流程)
├── standalone_dedup.py     # 独立去重工具
├── standalone_upload.py    # 独立上传工具
├── setup_config.py         # 配置向导
├── flush_device_id.py      # 设备 ID 刷新脚本
└── requirements.txt        # Python 依赖
```

## 🛠️ 工具脚本

### 主程序
- `main.py` - 完整自动化流程 (下载 → 去重 → 上传)
- `start.bat` - 启动主程序

### 独立工具
- `standalone_dedup.py` - 独立视频去重工具
- `standalone_upload.py` - 独立视频上传工具
- `run_dedup.bat` - 运行去重工具
- `run_upload.bat` - 运行上传工具

### 配置工具
- `setup.bat` - 安装依赖
- `setup_douyin.bat` - 配置抖音采集
- `flush_device_id.py` - 刷新设备 ID
- `config_loader.py` - 测试配置加载


如果这个项目对你有帮助，请点亮 ⭐!

## 📜 开源协议

本项目基于 MIT 协议开源。详情请见 [LICENSE](LICENSE) 文件。


**注意**: 本工具仅供学习交流使用，请遵守相关平台的使用条款，不要用于商业用途或侵犯他人权益。
