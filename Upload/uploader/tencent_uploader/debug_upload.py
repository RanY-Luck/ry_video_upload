import asyncio
from pathlib import Path
from Upload.uploader.tencent_uploader.main import TencentVideo
from Upload.utils.config_loader import config

# 配置测试参数
VIDEO_PATH = r"F:\gitpush\ry_video_upload\Upload\videos\test_video.mp4"  # 修改为您要测试的视频路径
TITLE = "测试标题"
TAGS = ["测试标签1", "测试标签2"]


async def debug_upload():
    video_path = Path(VIDEO_PATH)
    if not video_path.exists():
        print(f"❌ 视频文件不存在: {VIDEO_PATH}")
        # 如果没有测试视频，创建一个空的占位文件仅用于测试逻辑（实际上传步骤可能会失败）
        # video_path.touch()
        # print(f"⚠️ 已创建空测试文件: {VIDEO_PATH}") 
        return

    account_file = config.get_path('account_file')
    if not account_file.exists():
        print(f"❌ 账号文件不存在: {account_file}")
        print("请先运行 standalone_upload.py 或 Upload/vx_cookie.py 获取 Cookie")
        return

    print(f"开始调试上传: {video_path}")

    # 实例化上传器
    uploader = TencentVideo(
        title=TITLE,
        file_path=video_path,
        tags=TAGS,
        account_file=account_file,
        category=config.upload_category
    )

    # 启动 Playwright 并开始上传
    # 注意: upload 方法内部已经包含了 browser.launch(headless=False)
    # 所以会弹出浏览器窗口，方便您观察

    # 为了方便调试，您可以修改 TencentVideo.upload 方法，
    # 在关键步骤加入 await page.pause() 来暂停执行，打开 Playwright 检查器

    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        await uploader.upload(p)


if __name__ == "__main__":
    try:
        asyncio.run(debug_upload())
    except KeyboardInterrupt:
        print("\n调试已停止")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
