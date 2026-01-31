# -*- coding: utf-8 -*-
import json
import os
import asyncio
from datetime import datetime
from playwright.async_api import Playwright, async_playwright
from Upload.conf import LOCAL_CHROME_PATH
from Upload.utils.base_social_media import set_init_script
from Upload.utils.files_times import get_absolute_path
from Upload.utils.log import tencent_logger


def is_docker_environment() -> bool:
    """
    检测是否在 Docker 环境中运行
    
    检测方式:
    1. 检查 /.dockerenv 文件是否存在
    2. 检查环境变量 DOCKER_ENV
    3. 检查 /proc/1/cgroup 中是否包含 docker
    
    Returns:
        bool: True 表示在 Docker 环境中
    """
    # 方式1: 检查 .dockerenv 文件
    if os.path.exists('/.dockerenv'):
        return True

    # 方式2: 检查环境变量
    if os.environ.get('DOCKER_ENV', '').lower() in ('true', '1', 'yes'):
        return True

    # 方式3: 检查 cgroup (Linux 特有)
    try:
        with open('/proc/1/cgroup', 'r') as f:
            if 'docker' in f.read():
                return True
    except (FileNotFoundError, PermissionError):
        pass

    return False


def format_str_for_short_title(origin_title: str) -> str:
    # 定义允许的特殊字符
    allowed_special_chars = "《》“”:+?%°"

    # 移除不允许的特殊字符
    filtered_chars = [char if char.isalnum() or char in allowed_special_chars else ' ' if char == ',' else '' for
                      char in origin_title]
    formatted_string = ''.join(filtered_chars)

    # 调整字符串长度
    if len(formatted_string) > 16:
        # 截断字符串
        formatted_string = formatted_string[:16]
    elif len(formatted_string) < 6:
        # 使用空格来填充字符串
        formatted_string += ' ' * (6 - len(formatted_string))

    return formatted_string


async def cookie_auth(account_file):
    """验证 cookie 和登录状态是否有效
    
    优化后的验证策略:
    1. 只验证 Cookie 文件的完整性和过期时间
    2. 不进行实际页面访问验证(避免触发微信风控)
    3. 真正的登录验证会在上传时进行(使用有头浏览器,不会触发风控)
    
    Returns:
        bool: True 表示 Cookie 文件有效, False 表示需要重新登录
    """
    try:
        # 第一步: 读取并检查 account.json 文件
        tencent_logger.info("[+] 开始验证登录状态...")
        with open(account_file, 'r', encoding='utf-8') as f:
            account_data = json.load(f)

        # 检查必要的 cookie 字段
        cookies = account_data.get('cookies', [])
        sessionid_cookie = None
        wxuin_cookie = None

        for cookie in cookies:
            if cookie.get('name') == 'sessionid':
                sessionid_cookie = cookie
            elif cookie.get('name') == 'wxuin':
                wxuin_cookie = cookie

        if not sessionid_cookie or not wxuin_cookie:
            tencent_logger.error("[+] Cookie 缺少必要字段 (sessionid 或 wxuin)")
            return False

        # 检查 sessionid 是否过期
        expires = sessionid_cookie.get('expires', 0)
        current_timestamp = datetime.now().timestamp()

        if expires <= current_timestamp:
            tencent_logger.error(f"[+] Cookie 已过期 (过期时间: {datetime.fromtimestamp(expires)})")
            return False

        tencent_logger.info(f"[+] Cookie 有效期至: {datetime.fromtimestamp(expires)}")

        # 检查 localStorage 中的关键字段 (可选验证)
        origins = account_data.get('origins', [])
        if not origins:
            tencent_logger.warning("[!] LocalStorage 数据缺失 (跳过严格检查)")
        else:
            local_storage = origins[0].get('localStorage', [])
            has_finder_username = False
            has_device_id = False

            for item in local_storage:
                if item.get('name') == 'finder_username':
                    has_finder_username = True
                    tencent_logger.info(f"[+] 视频号用户名: {item.get('value', 'N/A')}")
                elif item.get('name') == '_finger_print_device_id':
                    has_device_id = True
                    tencent_logger.info(f"[+] 设备指纹: {item.get('value', 'N/A')}")

            if not has_finder_username or not has_device_id:
                tencent_logger.warning("[!] LocalStorage 缺少关键字段 (仅警告,继续尝试使用 Cookie)")
            
        # ✅ 基础验证通过 (只要 Cookie 没过期且包含必要字段,就尝试使用)
        tencent_logger.success("[+] ✅ Cookie 文件初步验证通过")
        return True

    except FileNotFoundError:
        tencent_logger.error(f"[+] Cookie 文件不存在: {account_file}")
        return False
    except json.JSONDecodeError:
        tencent_logger.error(f"[+] Cookie 文件格式错误: {account_file}")
        return False
    except Exception as e:
        tencent_logger.error(f"[+] 验证登录状态时出错: {e}")
        return False


async def get_tencent_cookie(account_file):
    async with async_playwright() as playwright:
        options = {
            'args': [
                '--lang en-GB'
            ],
            'headless': False,  # Set headless option here
        }
        # Make sure to run headed.
        browser = await playwright.chromium.launch(**options)
        # Setup context however you like.
        context = await browser.new_context()  # Pass any options
        # Pause the page, and start recording manually.
        context = await set_init_script(context)
        page = await context.new_page()
        await page.goto("https://channels.weixin.qq.com")
        await page.pause()
        # 点击调试器的继续，保存cookie
        await context.storage_state(path=account_file)


async def weixin_setup(account_file, handle=False):
    """设置视频号账号登录
    
    由于视频号的安全机制,每次上传都需要重新验证身份
    因此直接打开浏览器进行扫码登录
    
    在 Docker 环境中,会通过 Bark 推送二维码到手机
    
    Args:
        account_file: 账号文件路径
        handle: 是否自动处理登录流程
    
    Returns:
        bool: 登录是否成功
    """
    if not os.path.isabs(account_file):
        account_file = get_absolute_path(account_file, "tencent_uploader")

    if not handle:
        # 如果不自动处理,只检查文件是否存在
        return os.path.exists(account_file)

    # 检测 Docker 环境
    if is_docker_environment():
        tencent_logger.info('[+] 检测到 Docker 环境，使用 Bark 推送二维码登录...')
        try:
            from Upload.uploader.tencent_uploader.docker_qr_login import DockerQRLogin
            docker_login = DockerQRLogin(account_file, timeout=180)
            return await docker_login.docker_login()
        except ImportError as e:
            tencent_logger.error(f'[+] Docker 登录模块导入失败: {e}')
            return False
        except Exception as e:
            tencent_logger.error(f'[+] Docker 登录失败: {e}')
            return False

    # 非 Docker 环境: 直接打开浏览器进行扫码登录
    tencent_logger.info('[+] 正在打开浏览器,请使用微信扫码登录...')
    tencent_logger.info('[+] 登录成功后,点击调试器的"继续"按钮')

    try:
        await get_tencent_cookie(account_file)
        tencent_logger.success('[+] ✅ 登录成功,已保存登录信息')
        return True
    except Exception as e:
        tencent_logger.error(f'[+] ❌ 登录失败: {e}')
        return False


class TencentVideo(object):
    def __init__(self, title, file_path, tags, account_file, category=None):
        self.title = title  # 视频标题
        self.file_path = file_path
        self.tags = tags
        self.account_file = account_file
        self.category = category
        self.local_executable_path = LOCAL_CHROME_PATH



    async def handle_upload_error(self, page):
        tencent_logger.info("视频出错了，重新上传中")
        await page.locator('div.media-status-content div.tag-inner:has-text("删除")').click()
        await page.get_by_role('button', name="删除", exact=True).click()
        file_input = page.locator('input[type="file"]')
        await file_input.set_input_files(self.file_path)

    async def handle_login_redirect(self, page, context):
        """检测并处理登录重定向"""
        try:
            # 等待几秒让重定向发生
            await asyncio.sleep(3)
            
            # 检测是否在登录页面
            # 1. URL 检查
            is_login_url = "/login" in page.url or page.url == "https://channels.weixin.qq.com/"
            # 2. 页面元素检查
            current_text = await page.content()
            has_login_text = "微信扫码" in current_text or "使用微信" in current_text
            
            if is_login_url or has_login_text:
                tencent_logger.warning("⚠️ 检测到需要登录 (Cookie失效或被重定向)")
                tencent_logger.info("📱 请在浏览器中扫描二维码登录...")
                
                # 发送 Bark 通知 (如果配置了)
                try:
                    from Upload.utils.config_loader import config
                    from Upload.utils.bark_notifier import BarkNotifier
                    notifier = BarkNotifier(config.bark_key)
                    notifier.send(
                        title="📱 需要手动扫码",
                        content="上传被重定向到登录页，请在服务器/浏览器扫码",
                        sound="alarm",
                        level="timeSensitive"
                    )
                except Exception as e:
                    tencent_logger.debug(f"发送通知失败: {e}")

                # 循环等待直到登录成功
                while True:
                    if "channels.weixin.qq.com/platform" in page.url:
                        tencent_logger.success("✅ 检测到 URL 变更为后台地址，登录成功！")
                        break
                    
                    # 检查昵称元素
                    if await page.locator("div.finder-nickname").count() > 0:
                        tencent_logger.success("✅ 检测到用户信息，登录成功！")
                        break
                        
                    await asyncio.sleep(2)
                
                # 登录成功后保存 Cookie
                await context.storage_state(path=f"{self.account_file}")
                tencent_logger.info("💾 新的登录状态已保存")
                
                # 重新进入发布页面
                await page.goto("https://channels.weixin.qq.com/platform/post/create")
                await asyncio.sleep(3)

        except Exception as e:
            tencent_logger.error(f"处理登录重定向时出错: {e}")

    async def upload(self, playwright: Playwright) -> None:
        # 使用 Chromium (这里使用系统内浏览器，用chromium 会造成h264错误
        browser = await playwright.chromium.launch(headless=False, executable_path=self.local_executable_path)
        # 创建一个浏览器上下文，使用指定的 cookie 文件
        context = await browser.new_context(storage_state=f"{self.account_file}")
        context = await set_init_script(context)

        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://channels.weixin.qq.com/platform/post/create")
        tencent_logger.info(f'[+]正在上传-------{self.title}.mp4')
        
        # 【新增】检测是否被重定向到登录页
        await self.handle_login_redirect(page, context)

        # 等待页面跳转到指定的 URL，没进入，则自动等待到超时
        await page.wait_for_url("https://channels.weixin.qq.com/platform/post/create")
        # await page.wait_for_selector('input[type="file"]', timeout=10000)
        file_input = page.locator('input[type="file"]')
        await file_input.set_input_files(self.file_path)
        # 填充标题和话题
        await self.add_title_tags(page)
        # 添加商品
        # await self.add_product(page)
        # 合集功能
        await self.add_collection(page)
        # 原创选择
        await self.add_original(page)
        # 检测上传状态
        await self.detect_upload_status(page)
        # 添加短标题
        await self.add_short_title(page)

        await self.click_publish(page)

        await context.storage_state(path=f"{self.account_file}")  # 保存cookie
        tencent_logger.success('  [-]cookie更新完毕！')
        await asyncio.sleep(2)  # 这里延迟是为了方便眼睛直观的观看
        # 关闭浏览器上下文和浏览器实例
        await context.close()
        await browser.close()

    async def add_short_title(self, page):
        short_title_element = page.get_by_text("短标题", exact=True).locator("..").locator(
            "xpath=following-sibling::div"
        ).locator(
            'span input[type="text"]'
        )
        if await short_title_element.count():
            short_title = format_str_for_short_title(self.title)
            await short_title_element.fill(short_title)

    async def click_publish(self, page):
        while True:
            try:
                publish_buttion = page.locator('div.form-btns button:has-text("发表")')
                if await publish_buttion.count():
                    await publish_buttion.click()
                await page.wait_for_url("https://channels.weixin.qq.com/platform/post/list", timeout=10000)
                tencent_logger.success("  [-]视频发布成功")
                break
            except Exception as e:
                current_url = page.url
                if "https://channels.weixin.qq.com/platform/post/list" in current_url:
                    tencent_logger.success("  [-]视频发布成功")
                    break
                else:
                    tencent_logger.exception(f"  [-] Exception: {e}")
                    tencent_logger.info("  [-] 视频正在发布中...")
                    await asyncio.sleep(0.5)

    async def detect_upload_status(self, page):
        while True:
            # 匹配删除按钮，代表视频上传完毕，如果不存在，代表视频正在上传，则等待
            try:
                # 匹配删除按钮，代表视频上传完毕
                if "weui-desktop-btn_disabled" not in await page.get_by_role("button", name="发表").get_attribute(
                        'class'
                ):
                    tencent_logger.info("  [-]视频上传完毕")
                    break
                else:
                    tencent_logger.info("  [-] 正在上传视频中...")
                    await asyncio.sleep(2)
                    # 出错了视频出错
                    if await page.locator('div.status-msg.error').count() and await page.locator(
                            'div.media-status-content div.tag-inner:has-text("删除")'
                    ).count():
                        tencent_logger.error("  [-] 发现上传出错了...准备重试")
                        await self.handle_upload_error(page)
            except:
                tencent_logger.info("  [-] 正在上传视频中...")
                await asyncio.sleep(2)

    async def add_title_tags(self, page):
        await page.locator("div.input-editor").click()
        await page.keyboard.type(self.title)
        await page.keyboard.press("Enter")
        for index, tag in enumerate(self.tags, start=1):
            await page.keyboard.type("#" + tag)
            await page.keyboard.press("Space")
        tencent_logger.info(f"成功添加hashtag: {len(self.tags)}")

    async def add_collection(self, page):
        collection_elements = page.get_by_text("添加到合集").locator("xpath=following-sibling::div").locator(
            '.option-list-wrap > div'
        )
        if await collection_elements.count() > 1:
            await page.get_by_text("添加到合集").locator("xpath=following-sibling::div").click()
            await collection_elements.first.click()

    async def add_original(self, page):
        if await page.get_by_label("视频为原创").count():
            await page.get_by_label("视频为原创").check()
        # 检查 "我已阅读并同意 《视频号原创声明使用条款》" 元素是否存在
        label_locator = await page.locator('label:has-text("我已阅读并同意 《视频号原创声明使用条款》")').is_visible()
        if label_locator:
            await page.get_by_label("我已阅读并同意 《视频号原创声明使用条款》").check()
            await page.get_by_role("button", name="声明原创").click()
        # 2023年11月20日 wechat更新: 可能新账号或者改版账号，出现新的选择页面
        if await page.locator('div.label span:has-text("声明原创")').count() and self.category:
            # 因处罚无法勾选原创，故先判断是否可用
            if not await page.locator('div.declare-original-checkbox input.ant-checkbox-input').is_disabled():
                await page.locator('div.declare-original-checkbox input.ant-checkbox-input').click()
                if not await page.locator(
                        'div.declare-original-dialog label.ant-checkbox-wrapper.ant-checkbox-wrapper-checked:visible'
                ).count():
                    await page.locator('div.declare-original-dialog input.ant-checkbox-input:visible').click()
            if await page.locator('div.original-type-form > div.form-label:has-text("原创类型"):visible').count():
                await page.locator('div.form-content:visible').click()  # 下拉菜单
                await page.locator(
                    f'div.form-content:visible ul.weui-desktop-dropdown__list li.weui-desktop-dropdown__list-ele:has-text("{self.category}")'
                ).first.click()
                await page.wait_for_timeout(1000)
            if await page.locator('button:has-text("声明原创"):visible').count():
                await page.locator('button:has-text("声明原创"):visible').click()

    async def main(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)
