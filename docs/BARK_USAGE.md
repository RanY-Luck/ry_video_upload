# BarkNotifier 使用指南

`BarkNotifier` 是一个封装了 Bark 推送服务的 Python 类，让您可以轻松地在 Python 项目中发送 iOS 推送通知。

## 1. 安装依赖

本模块依赖 `requests` 库，如果尚未安装，请运行：

```bash
pip install requests
```

## 2. 快速开始

将 `bark_notifier.py` 文件复制到您的项目目录中，然后按如下方式使用：

```python
from Upload.utils.bark_notifier import BarkNotifier

# 初始化（将 YOUR_KEY 替换为您在 Bark App 中获取的 Key）
notifier = BarkNotifier("YOUR_KEY")

# 发送简单通知
notifier.send("测试标题", "这是一条测试消息")
```

## 3. 高级功能示例

`send()` 方法支持 Bark 的所有官方参数，以下是一些常用场景：

### 3.1 推送带音乐的通知 🎵
```python
notifier.send(
    title="音乐通知",
    content="这条消息有铃声",
    sound="minuet"  # 支持 alarm, bell, minuet, calypso 等 30+ 种铃声
)
```

### 3.2 持续响铃（类似来电）📞
```python
notifier.send(
    title="紧急呼叫",
    content="请立即回复！",
    call=1,        # 持续响铃
    sound="alarm"
)
```

### 3.3 重要警报（绕过静音/勿扰）🚨
```python
notifier.send(
    title="严重警告",
    content="服务器宕机！",
    level="critical",  # 关键级别
    volume=10,         # 最大音量
    sound="alarm"
)
```

### 3.4 带图片的通知 🖼️
```python
notifier.send(
    title="监控截图",
    content="检测到移动物体",
    image="https://example.com/snapshot.jpg"
)
```

### 3.5 点击跳转 🔗
```python
notifier.send(
    title="打开百度",
    content="点击跳转到百度",
    url="https://www.baidu.com"
)
```

### 3.6 自动复制验证码 📋
```python
notifier.send(
    title="验证码",
    content="您的验证码是 8888",
    auto_copy=1,   # 自动复制 content
    copy="8888"    # 或者指定要复制的内容
)
```

## 4. 参数列表

`send()` 方法支持以下所有参数（均为可选）：

| 参数名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `title` | str | **必填**，通知标题 |
| `content` | str | 通知内容 |
| `sound` | str | 铃声名称 (minuet, alarm, bell, etc.) |
| `group` | str | 通知分组 |
| `icon` | str | 自定义图标 URL |
| `image` | str | 通知图片 URL |
| `url` | str | 点击跳转 URL |
| `level` | str | `active`, `timeSensitive`, `passive`, `critical` |
| `badge` | int | App 角标数字 |
| `auto_copy` | int | 设为 1 自动复制内容 |
| `copy` | str | 指定复制的文本 |
| `is_archive` | int | 设为 1 自动归档 |

## 5. 项目集成建议

建议将 `bark_notifier.py` 放在项目的 `utils` 或 `common` 目录下，方便统一调用。

```python
# 示例：在 utils/notification.py 中使用
from .bark_notifier import BarkNotifier
import os

# 从环境变量获取 Key，避免硬编码
BARK_KEY = os.getenv("BARK_KEY")

def send_alert(message):
    if BARK_KEY:
        notifier = BarkNotifier(BARK_KEY)
        notifier.send("系统警报", message, level="timeSensitive")
```
