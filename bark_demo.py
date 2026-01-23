#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Bark 推送通知 Demo 脚本

Bark 是一个 iOS 推送通知服务，可以通过简单的 HTTP 请求发送推送到 iPhone。
使用前需要：
1. 在 iPhone 上安装 Bark App
2. 获取你的 Bark 推送 Key（在 App 中可以看到）
"""
import sys
import time
from Upload.utils.bark_notifier import BarkNotifier
from Upload.utils.config_loader import config


def demo_basic_push(bark_key: str):
    """演示 1：基础推送"""
    print("\n=== 演示 1: 基础推送 ===")
    notifier = BarkNotifier(bark_key)
    notifier.send(
        title="测试推送",
        content="这是一条来自 Bark Demo 的测试消息"
    )


def demo_with_sound(bark_key: str):
    """演示 2：带声音的推送"""
    print("\n=== 演示 2: 带声音的推送 ===")
    notifier = BarkNotifier(bark_key)
    notifier.send(
        title="重要通知",
        content="这条消息会发出警报声",
        sound="alarm"
    )


def demo_music_sounds(bark_key: str):
    """演示 3：音乐铃声（Bark 支持 30+ 种铃声）"""
    print("\n=== 演示 3: 音乐铃声 ===")
    notifier = BarkNotifier(bark_key)

    # 音乐铃声示例 1: Minuet（小步舞曲）
    notifier.send(
        title="🎵 音乐铃声 - Minuet",
        content="优雅的小步舞曲铃声",
        sound="minuet"
    )

    time.sleep(2)

    # 音乐铃声示例 2: Calypso（卡吕普索）
    notifier.send(
        title="🎵 音乐铃声 - Calypso",
        content="轻快的加勒比风格铃声",
        sound="calypso"
    )

    time.sleep(2)

    # 音乐铃声示例 3: Chime（钟声）
    notifier.send(
        title="🎵 音乐铃声 - Chime",
        content="清脆的钟声铃声",
        sound="chime"
    )


def demo_continuous_call(bark_key: str):
    """演示 4：持续响铃（类似来电效果）"""
    print("\n=== 演示 4: 持续响铃 ===")
    notifier = BarkNotifier(bark_key)
    notifier.send(
        title="📞 重要来电",
        content="这条消息会持续响铃，直到你点击通知",
        sound="alarm",
        call=1  # 设置为 1 启用持续响铃
    )


def demo_time_sensitive(bark_key: str):
    """演示 5：时间敏感通知"""
    print("\n=== 演示 5: 时间敏感通知 ===")
    notifier = BarkNotifier(bark_key)
    notifier.send(
        title="⏰ 时间敏感通知",
        content="这条通知会突破专注模式显示",
        level="timeSensitive",  # 时间敏感级别
        sound="bell",
        icon="https://api.iconify.design/mdi:clock-alert.svg"
    )


def demo_critical_alert(bark_key: str):
    """演示 6：关键警报（绕过勿扰模式）"""
    print("\n=== 演示 6: 关键警报 ===")
    notifier = BarkNotifier(bark_key)
    notifier.send(
        title="🚨 关键警报",
        content="此警报会绕过勿扰模式，即使静音也会响铃！",
        level="critical",  # 关键级别
        volume=10,  # 最大音量
        sound="alarm"
    )


def demo_with_url(bark_key: str):
    """演示 7：带跳转链接的推送"""
    print("\n=== 演示 7: 带跳转链接的推送 ===")
    notifier = BarkNotifier(bark_key)
    notifier.send(
        title="查看详情",
        content="点击这条消息将打开百度",
        url="https://www.baidu.com"
    )


def demo_with_group(bark_key: str):
    """演示 8：分组推送"""
    print("\n=== 演示 8: 分组推送 ===")
    notifier = BarkNotifier(bark_key)
    notifier.send(
        title="视频处理完成",
        content="已成功处理 5 个视频文件",
        group="视频处理",
        icon="https://api.iconify.design/mdi:video.svg"
    )


def demo_with_copy(bark_key: str):
    """演示 9：自动复制内容"""
    print("\n=== 演示 9: 自动复制内容 ===")
    notifier = BarkNotifier(bark_key)
    notifier.send(
        title="验证码",
        content="您的验证码是 123456",
        copy="123456"  # 点击推送后会自动复制到剪贴板
    )


def demo_with_image(bark_key: str):
    """演示 10：带图片的推送"""
    print("\n=== 演示 10: 带图片的推送 ===")
    notifier = BarkNotifier(bark_key)
    notifier.send(
        title="图片推送",
        content="这是一条带图片的推送通知",
        image="https://picsum.photos/400/300",  # 示例图片
        sound="bell"
    )


def demo_with_markdown(bark_key: str):
    """演示 11：Markdown 格式推送"""
    print("\n=== 演示 11: Markdown 格式推送 ===")
    notifier = BarkNotifier(bark_key)
    notifier.send(
        title="Markdown 示例",
        content="# 标题\n## 二级标题\n**粗体文本**\n*斜体文本*\n- 列表项 1\n- 列表项 2",
        markdown=1  # 启用 Markdown 渲染
    )


def demo_with_subtitle(bark_key: str):
    """演示 12：带副标题的推送"""
    print("\n=== 演示 12: 带副标题的推送 ===")
    notifier = BarkNotifier(bark_key)
    notifier.send(
        title="主标题",
        subtitle="这是副标题",
        content="这是详细内容",
        sound="bell"
    )


def demo_video_processing_notification(bark_key: str):
    """演示 13：视频处理场景（综合示例）"""
    print("\n=== 演示 13: 视频处理场景 ===")
    notifier = BarkNotifier(bark_key)

    # 模拟视频处理流程的推送
    notifier.send(
        title="视频上传任务",
        content="开始处理 10 个视频文件...",
        group="视频处理",
        sound="bell"
    )

    # 模拟处理完成
    time.sleep(2)

    notifier.send(
        title="视频上传完成",
        subtitle="视频处理结果",
        content="✅ 成功: 8个\n❌ 失败: 2个",
        group="视频处理",
        sound="multiwayinvitation",
        badge=2,  # 显示角标数字
        icon="https://api.iconify.design/mdi:check-circle.svg"
    )


def demo_all_sounds(bark_key: str):
    """演示 14：所有可用铃声列表"""
    print("\n=== 演示 14: 所有可用铃声 ===")
    print("Bark 支持以下 30+ 种铃声：")

    sounds = [
        "alarm", "anticipate", "bell", "birdsong", "bloom",
        "calypso", "chime", "choo", "descent", "electronic",
        "fanfare", "glass", "gotosleep", "healthnotification", "horn",
        "ladder", "mailsent", "minuet", "multiwayinvitation", "newmail",
        "newsflash", "noir", "paymentsuccess", "shake", "sherwoodforest",
        "silence", "spell", "suspense", "telegraph", "tiptoes",
        "typewriters", "update"
    ]

    for sound in sounds:
        print(f"  - {sound}")

    print("\n你可以在 send() 方法中使用 sound 参数来指定任意铃声")


def run_all_demos(bark_key: str):
    """运行所有演示"""
    print("\n🚀 开始运行所有演示...\n")


    # 为了避免推送过快，在每个演示之间添加延迟
    demos = [
        demo_basic_push,
        demo_with_sound,
        demo_music_sounds,
        demo_continuous_call,
        demo_time_sensitive,
        demo_critical_alert,
        demo_with_url,
        demo_with_group,
        demo_with_copy,
        demo_with_image,
        demo_with_markdown,
        demo_with_subtitle,
        demo_video_processing_notification,
        demo_all_sounds,
    ]

    for i, demo in enumerate(demos, 1):
        print(f"\n[{i}/{len(demos)}] ", end="")
        demo(bark_key)
        if i < len(demos):  # 最后一个演示不需要等待
            time.sleep(3)  # 每个演示之间等待 3 秒


def main():
    """主函数"""
    print("=" * 60)
    print("Bark 推送通知 Demo - 完整功能展示")
    print("=" * 60)

    # 请在这里填入你的 Bark Key
    # 获取方式：在 iPhone 上安装 Bark App，打开后可以看到你的推送地址
    # 格式类似：https://api.day.app/YOUR_KEY/
    # 只需要填写 YOUR_KEY 部分
    BARK_KEY = "aG2Msu9QWoPCZ8sk6Jbqne"
    # BARK_KEY = config.bark_key
    print("BARK_KEY")
    if BARK_KEY == "YOUR_BARK_KEY_HERE":
        print("\n⚠️  请先在脚本中设置你的 BARK_KEY！")
        print("获取方式：")
        print("1. 在 iPhone 上安装 Bark App")
        print("2. 打开 App，可以看到类似 'https://api.day.app/YOUR_KEY/' 的地址")
        print("3. 将 YOUR_KEY 部分填入本脚本的 BARK_KEY 变量")
        return

    print("\n请选择要运行的演示：")
    print("  0. 运行全部演示")
    print("  1. 基础推送")
    print("  2. 带声音的推送")
    print("  3. 音乐铃声 🎵")
    print("  4. 持续响铃（来电效果）📞")
    print("  5. 时间敏感通知 ⏰")
    print("  6. 关键警报（绕过勿扰）🚨")
    print("  7. 带跳转链接")
    print("  8. 分组推送")
    print("  9. 自动复制内容")
    print(" 10. 带图片的推送")
    print(" 11. Markdown 格式")
    print(" 12. 带副标题")
    print(" 13. 视频处理场景")
    print(" 14. 查看所有可用铃声")

    # 简化为直接运行所有演示（也可以改为交互式选择）
    if len(sys.argv) > 1:
        choice = sys.argv[1]
        print(f"收到命令行参数: {choice}")
    else:
        choice = input("\n请输入选项（0-14，回车默认运行全部）：").strip()

    if not choice:
        choice = "0"

    demos = {
        "0": lambda: run_all_demos(BARK_KEY),
        "1": lambda: demo_basic_push(BARK_KEY),
        "2": lambda: demo_with_sound(BARK_KEY),
        "3": lambda: demo_music_sounds(BARK_KEY),
        "4": lambda: demo_continuous_call(BARK_KEY),
        "5": lambda: demo_time_sensitive(BARK_KEY),
        "6": lambda: demo_critical_alert(BARK_KEY),
        "7": lambda: demo_with_url(BARK_KEY),
        "8": lambda: demo_with_group(BARK_KEY),
        "9": lambda: demo_with_copy(BARK_KEY),
        "10": lambda: demo_with_image(BARK_KEY),
        "11": lambda: demo_with_markdown(BARK_KEY),
        "12": lambda: demo_with_subtitle(BARK_KEY),
        "13": lambda: demo_video_processing_notification(BARK_KEY),
        "14": lambda: demo_all_sounds(BARK_KEY),
    }

    if choice in demos:
        demos[choice]()
    else:
        print(f"\n❌ 无效选项: {choice}")
        return

    print("\n" + "=" * 60)
    print("演示完成！请检查你的 iPhone 推送通知。")
    print("=" * 60)


if __name__ == "__main__":
    main()
