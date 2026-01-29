# -*- coding: utf-8 -*-
"""
Docker 环境二维码登录模块

功能: 在无图形界面的 Docker 容器中，通过 Bark 推送二维码图片实现微信视频号登录
"""
import asyncio
import base64
import httpx
from pathlib import Path
from typing import Optional, Tuple
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from Upload.utils.bark_notifier import BarkNotifier
from Upload.utils.base_social_media import set_init_script
from Upload.utils.config_loader import config
from Upload.utils.log import tencent_logger


class DockerQRLogin:
    """Docker 环境二维码登录类"""

    # 微信视频号登录页
    LOGIN_URL = "https://channels.weixin.qq.com"

    # 登录成功后的 URL 特征
    SUCCESS_URL_PATTERN = "channels.weixin.qq.com/platform"

    # sm.ms 图床 API
    SMMS_API_URL = "https://sm.ms/api/v2/upload"

    def __init__(self, account_file: Path, timeout: int = 180):
        """
        初始化 Docker 登录器
        
        Args:
            account_file: 账号文件保存路径
            timeout: 等待扫码超时时间（秒）
        """
        self.account_file = Path(account_file)
        self.timeout = timeout
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

        # Bark 通知器
        try:
            self.notifier = BarkNotifier(config.bark_key)
        except Exception as e:
            tencent_logger.warning(f"[Docker登录] Bark 初始化失败: {e}")
            self.notifier = None

    async def _init_browser(self) -> None:
        """初始化 headless 浏览器"""
        tencent_logger.info("[Docker登录] 正在初始化 headless 浏览器 (反爬增强版)...")

        playwright = await async_playwright().start()

        # 启动参数优化，尽可能模拟真实浏览器
        args = [
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-blink-features=AutomationControlled',  # 关键：禁用自动化控制特征
            '--disable-infobars',
            '--window-size=1920,1080',
        ]

        self.browser = await playwright.chromium.launch(
            headless=True,
            args=args
        )

        # 使用自定义的 User-Agent
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="zh-CN",
            timezone_id="Asia/Shanghai"
        )

        # 注入反爬脚本 (Stealth)
        await self.context.add_init_script(
            """
                        Object.defineProperty(navigator, 'webdriver', {
                            get: () => undefined
                        });
                        // 覆盖 chrome 对象
                        window.chrome = {
                            runtime: {}
                        };
                        // 覆盖 plugins
                        Object.defineProperty(navigator, 'plugins', {
                            get: () => [1, 2, 3, 4, 5]
                        });
                        // 覆盖 languages
                        Object.defineProperty(navigator, 'languages', {
                            get: () => ['zh-CN', 'zh']
                        });
                    """
        )

        self.context = await set_init_script(self.context)
        self.page = await self.context.new_page()

        tencent_logger.info("[Docker登录] 浏览器初始化完成")

    async def _simulate_human_behavior(self):
        """模拟人类操作行为"""
        try:
            # 随机移动鼠标
            await self.page.mouse.move(100, 100)
            await asyncio.sleep(0.5)
            await self.page.mouse.move(200, 200)

            # 滚动页面
            await self.page.evaluate("window.scrollTo(0, 500)")
            await asyncio.sleep(0.5)
            await self.page.evaluate("window.scrollTo(0, 0)")
        except Exception:
            pass

    async def _close_browser(self) -> None:
        """关闭浏览器"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        tencent_logger.info("[Docker登录] 浏览器已关闭")

    async def get_qr_code_image(self) -> Tuple[bytes, str]:
        """
        获取登录二维码图片
        
        Returns:
            Tuple[bytes, str]: (图片二进制数据, 二维码 src URL)
        """
        tencent_logger.info(f"[Docker登录] 正在访问登录页面: {self.LOGIN_URL}")

        # 设置较大的视口，避免布局问题
        await self.page.set_viewport_size({"width": 1920, "height": 1080})

        await self.page.goto(self.LOGIN_URL, wait_until="networkidle")

        # 模拟人类操作
        await self._simulate_human_behavior()

        # 保存页面加载后的全屏截图，用于调试
        await self.page.screenshot(path="images/tencent_load.png", full_page=True)
        tencent_logger.info("[Docker登录] 已保存页面调试截图: images/tencent_load.png")

        # 等待页面加载
        await asyncio.sleep(3)

        image_data = None

        # 尝试读取已保存的全屏截图
        try:
            if Path("images/tencent_load.png").exists():
                with open("images/tencent_load.png", "rb") as f:
                    image_data = f.read()
                tencent_logger.info("[Docker登录] 成功读取全屏截图作为二维码图片")
                # 返回空字符串作为 src，因为全屏截图没有单一的 URL
                return image_data, ""
        except Exception as e:
            tencent_logger.error(f"[Docker登录] 读取全屏截图失败: {e}")

        # 如果连全屏截图都没有
        tencent_logger.error("[Docker登录] 无法获取任何图片，保存失败截图和页面源码")
        await self.page.screenshot(path="debug_qr_failed.png")

        # 保存获取到的图片用于调试
        with open("images/debug_qr_element.png", "wb") as f:
            f.write(image_data)
        tencent_logger.info("[Docker登录] 二维码图片已保存至 debug_qr_element.png")

        return image_data

    async def upload_image_to_imgbb(self, image_data: bytes, api_key: str) -> Optional[str]:
        """
        上传图片到 imgbb 图床
        
        Args:
            image_data: 图片二进制数据
            api_key: imgbb API Key
            
        Returns:
            公网可访问的图片 URL
        """
        tencent_logger.info("[Docker登录] 正在上传二维码到 imgbb 图床...")

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                # imgbb 需要 base64 编码
                image_base64 = base64.b64encode(image_data).decode('utf-8')

                response = await client.post(
                    "https://api.imgbb.com/1/upload",
                    data={
                        'key': api_key,
                        'image': image_base64,
                        'name': 'wechat_qrcode'
                    }
                )

                result = response.json()

                if result.get('success'):
                    url = result['data']['url']
                    tencent_logger.info(f"[Docker登录] 图片上传成功: {url}")
                    return url
                else:
                    tencent_logger.error(f"[Docker登录] imgbb 上传失败: {result}")
                    return None

        except Exception as e:
            tencent_logger.error(f"[Docker登录] imgbb 上传异常: {e}")
            return None

    def send_qr_via_bark(self, image_url: str) -> bool:
        """
        通过 Bark 发送二维码图片推送
        
        Args:
            image_url: 公网可访问的二维码图片 URL
            
        Returns:
            推送是否成功
        """
        if not self.notifier:
            tencent_logger.error("[Docker登录] Bark 通知器未初始化")
            return False

        tencent_logger.info("[Docker登录] 正在通过 Bark 推送二维码...")

        try:
            result = self.notifier.send(
                title="🔐 视频号登录二维码",
                content=f"请使用微信扫描二维码完成登录\n⏰ 有效期约 {self.timeout} 秒",
                image=image_url,
                level="timeSensitive",
                sound="alarm",
                group="视频上传",
                icon="https://api.iconify.design/mdi:qrcode-scan.svg"
            )

            if result:
                tencent_logger.info("[Docker登录] ✅ Bark 推送成功，请检查手机")
            else:
                tencent_logger.error("[Docker登录] ❌ Bark 推送失败")

            return result

        except Exception as e:
            tencent_logger.error(f"[Docker登录] Bark 推送异常: {e}")
            return False

    async def wait_for_login(self) -> bool:
        """
        轮询检测登录状态
        
        Returns:
            是否登录成功
        """
        tencent_logger.info(f"[Docker登录] 等待扫码登录，超时时间: {self.timeout} 秒...")

        check_interval = 3  # 每 3 秒检查一次
        elapsed = 0

        while elapsed < self.timeout:
            try:
                current_url = self.page.url

                # 检查是否跳转到登录成功页面
                if self.SUCCESS_URL_PATTERN in current_url:
                    tencent_logger.info(f"[Docker登录] ✅ 检测到登录成功！URL: {current_url}")
                    return True

                # 检查是否有登录成功的元素
                try:
                    nickname = await self.page.wait_for_selector(
                        'div.finder-nickname, span.finder-nickname',
                        timeout=1000
                    )
                    if nickname:
                        tencent_logger.info("[Docker登录] ✅ 检测到用户昵称，登录成功！")
                        return True
                except Exception:
                    pass

                # 显示等待进度
                remaining = self.timeout - elapsed
                if elapsed % 15 == 0:  # 每 15 秒打印一次
                    tencent_logger.info(f"[Docker登录] 等待扫码中... 剩余 {remaining} 秒")

                await asyncio.sleep(check_interval)
                elapsed += check_interval

            except Exception as e:
                tencent_logger.error(f"[Docker登录] 检测登录状态时出错: {e}")
                await asyncio.sleep(check_interval)
                elapsed += check_interval

        tencent_logger.error(f"[Docker登录] ❌ 扫码超时（{self.timeout} 秒）")
        return False

    async def save_login_state(self) -> bool:
        """
        保存登录状态到账号文件
        
        Returns:
            是否保存成功
        """
        try:
            # 确保目录存在
            self.account_file.parent.mkdir(parents=True, exist_ok=True)

            # 保存 storage state
            await self.context.storage_state(path=str(self.account_file))
            tencent_logger.info(f"[Docker登录] ✅ 登录状态已保存: {self.account_file}")
            return True

        except Exception as e:
            tencent_logger.error(f"[Docker登录] 保存登录状态失败: {e}")
            return False

    def notify_login_success(self) -> None:
        """发送登录成功通知"""
        if self.notifier:
            try:
                self.notifier.send(
                    title="✅ 视频号登录成功",
                    content="已保存登录状态，可以开始上传视频了",
                    sound="fanfare",
                    group="视频上传",
                    icon="https://api.iconify.design/mdi:check-circle.svg"
                )
            except Exception as e:
                tencent_logger.warning(f"[Docker登录] 发送成功通知失败: {e}")

    def notify_login_failed(self, reason: str) -> None:
        """发送登录失败通知"""
        if self.notifier:
            try:
                self.notifier.send(
                    title="❌ 视频号登录失败",
                    content=reason,
                    sound="alarm",
                    level="timeSensitive",
                    group="视频上传",
                    icon="https://api.iconify.design/mdi:alert-circle.svg"
                )
            except Exception as e:
                tencent_logger.warning(f"[Docker登录] 发送失败通知失败: {e}")

    async def docker_login(self) -> bool:
        """
        Docker 环境完整登录流程
        
        流程:
        1. 初始化 headless 浏览器
        2. 获取二维码截图
        3. 上传到图床
        4. 通过 Bark 推送
        5. 轮询等待登录
        6. 保存 cookie
        
        Returns:
            登录是否成功
        """
        tencent_logger.info("[Docker登录] 开始 Docker 环境登录流程")

        try:
            # Step 1: 初始化浏览器
            await self._init_browser()

            # Step 2: 获取二维码
            qr_image, qr_src = await self.get_qr_code_image()

            if not qr_image:
                self.notify_login_failed("无法获取登录二维码")
                return False

            # Step 3: 上传到图床
            imgbb_key = config.get('IMGBB_API_KEY')
            image_url = await self.upload_image_to_imgbb(qr_image, imgbb_key)

            if not image_url:
                self.notify_login_failed("二维码上传图床失败")
                return False

            # Step 4: 通过 Bark 推送
            if not self.send_qr_via_bark(image_url):
                tencent_logger.warning("[Docker登录] Bark 推送失败，但继续等待登录...")

            # Step 5: 轮询等待登录
            if not await self.wait_for_login():
                self.notify_login_failed(f"扫码超时（{self.timeout} 秒）")
                return False

            # Step 6: 保存登录状态
            if not await self.save_login_state():
                self.notify_login_failed("保存登录状态失败")
                return False

            # 发送成功通知
            self.notify_login_success()
            tencent_logger.info("[Docker登录] ✅ Docker 环境登录成功！")

            return True

        except Exception as e:
            tencent_logger.error(f"[Docker登录] 登录过程出错: {e}")
            self.notify_login_failed(f"登录异常: {str(e)}")
            return False

        finally:
            await self._close_browser()


async def docker_qr_login(account_file: Path, timeout: int = 180) -> bool:
    """
    Docker 环境二维码登录便捷函数
    
    Args:
        account_file: 账号文件路径
        timeout: 超时时间（秒）
        
    Returns:
        登录是否成功
    """
    login = DockerQRLogin(account_file, timeout)
    return await login.docker_login()


# 测试入口
if __name__ == "__main__":
    async def demo():
        account_file = Path("test_account.json")
        login = DockerQRLogin(account_file, timeout=120)
        result = await login.docker_login()
        print(f"登录结果: {'成功' if result else '失败'}")
        return result


    success = asyncio.run(demo())
