#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小红书博主新帖实时监控脚本

功能：
  - 持续监控指定小红书博主的主页
  - 一旦发现新笔记立即下载（图片/视频/文案）
  - 通过 Bark 推送新帖通知到手机

使用方式：
  # 读取 .env 中 XHS_MONITOR_USERS 配置运行
  python xhs_monitor.py

  # 指定博主运行
  python xhs_monitor.py --users "https://www.xiaohongshu.com/user/profile/xxx"

  # 自定义检查间隔（秒）
  python xhs_monitor.py --interval 300

  # 仅检查一次不循环
  python xhs_monitor.py --once

  # 指定多个博主
  python xhs_monitor.py --users "url1,url2"
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
import httpx
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set
from dotenv import load_dotenv

# 将 XHS 模块路径加入 Python 搜索路径（必须在 import XHSDownloader 之前）
sys.path.insert(0, str(Path(__file__).parent / "XHS"))
from XHS.xhs_downloader import XHSDownloader

# ==========================================
# 日志配置
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("xhs_monitor")

# ==========================================
# 常量
# ==========================================
USER_URL_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?xiaohongshu\.com/user/profile/([a-zA-Z0-9_-]+)"
)


# ==========================================
# Bark 推送工具
# ==========================================
class BarkNotifier:
    """Bark iOS 推送通知"""

    def __init__(self, bark_key: str = ""):
        self.bark_key = bark_key or os.getenv("BARK_KEY", "").strip()
        self.base_url = "https://api.day.app"

    def is_enabled(self) -> bool:
        return bool(self.bark_key)

    async def push(
            self,
            title: str,
            body: str,
            url: str = "",
            group: str = "小红书监控",
    ) -> bool:
        """发送 Bark 推送通知（POST 方式）"""
        if not self.is_enabled():
            logger.warning("[Bark] 未配置 BARK_KEY，跳过推送")
            return False

        payload: Dict = {
            "title": title,
            "body": body,
            "group": group,
            "sound": "minuet",
        }
        if url:
            payload["url"] = url

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.base_url}/{self.bark_key}",
                    json=payload,
                )
                if resp.status_code == 200:
                    logger.info(f"[Bark] 推送成功: {title}")
                    return True
                else:
                    logger.warning(f"[Bark] 推送失败 HTTP {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"[Bark] 推送异常: {e}")
        return False


# ==========================================
# 单博主监控器
# ==========================================
class XHSBloggerMonitor:
    """
    监控单个小红书博主，检测新笔记并下载。
    """

    def __init__(
            self,
            user_url: str,
            download_dir: str,
            downloader: XHSDownloader,
            notifier: BarkNotifier,
            seen_file_dir: Path,
            cookie: str = "",
    ):
        """
        Args:
            user_url: 博主主页完整 URL
            download_dir: 下载根目录
            downloader: 已初始化的 XHSDownloader 实例
            notifier: Bark 推送实例
            seen_file_dir: 已知笔记 ID 记录文件目录
            cookie: 小红书 Cookie
        """
        self.user_url = user_url
        self.user_id = self._extract_user_id(user_url)
        self.download_dir = Path(download_dir)
        self.downloader = downloader
        self.notifier = notifier
        self.cookie = cookie or os.getenv("XHS_COOKIE", "")

        # 已知笔记 ID 持久化文件
        self.seen_file = seen_file_dir / f"{self.user_id}_seen.json"

        # 博主昵称（首次获取后缓存）
        self.author_name: str = ""

        # 内存中的已知笔记集合
        self._seen_ids: Set[str] = self._load_seen_ids()

        logger.info(f"[初始化] 博主 {self.user_id}，已知笔记数: {len(self._seen_ids)}")

    @staticmethod
    def _extract_user_id(url: str) -> str:
        """从 URL 中提取用户 ID"""
        match = USER_URL_PATTERN.search(url)
        return match.group(1) if match else url.strip()

    def _load_seen_ids(self) -> Set[str]:
        """从磁盘加载已知笔记 ID"""
        if not self.seen_file.exists():
            return set()
        try:
            with open(self.seen_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data.get("seen_ids", []))
        except Exception as e:
            logger.warning(f"[记录] 读取记录文件失败: {e}")
            return set()

    def _save_seen_ids(self):
        """将已知笔记 ID 持久化到磁盘"""
        try:
            self.seen_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.seen_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "user_id": self.user_id,
                        "author_name": self.author_name,
                        "seen_ids": list(self._seen_ids),
                        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            logger.error(f"[记录] 保存记录文件失败: {e}")

    async def _create_browser_context(self):
        """创建并配置 Playwright 浏览器上下文"""
        from playwright.async_api import async_playwright

        pw = await async_playwright().start()
        browser = await pw.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-infobars",
                "--window-size=1280,900",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
        )
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = {runtime: {}};
        """)

        # 注入 Cookie
        if self.cookie:
            cookies = []
            for item in self.cookie.split(";"):
                item = item.strip()
                if "=" in item:
                    name, value = item.split("=", 1)
                    cookies.append({
                        "name": name.strip(),
                        "value": value.strip(),
                        "domain": ".xiaohongshu.com",
                        "path": "/",
                    })
            if cookies:
                await context.add_cookies(cookies)
                logger.info(f"[浏览器] 已注入 {len(cookies)} 个 Cookie")

        return pw, browser, context

    async def _get_note_ids_from_dom(self, page) -> List[Dict]:
        """从页面 DOM 中提取笔记 ID 列表"""
        card_infos = await page.evaluate("""
            () => {
                const results = [];
                const seen = new Set();
                const selectors = [
                    'section.note-item a[href*="/explore/"]',
                    'section.note-item a[href*="/discovery/item/"]',
                    'div.note-item a[href*="/explore/"]',
                    'a[href*="/explore/"]',
                    'a[href*="/discovery/item/"]',
                ];
                for (const sel of selectors) {
                    const links = document.querySelectorAll(sel);
                    for (const a of links) {
                        const href = a.href || '';
                        const m = href.match(/\\/(explore|discovery\\/item)\\/([a-f0-9]+)/i);
                        if (!m) continue;
                        const noteId = m[2];
                        if (seen.has(noteId)) continue;
                        seen.add(noteId);
                        const titleEl = a.querySelector('.title, .note-title, span, footer span');
                        const title = (titleEl ? titleEl.textContent : '') || '';
                        results.push({
                            note_id: noteId,
                            title: title.trim().substring(0, 100),
                        });
                    }
                    if (results.length > 0) break;
                }
                return results;
            }
        """)
        return card_infos or []

    async def _extract_note_content(self, page) -> Dict:
        """从当前打开的笔记详情页提取内容（图片/视频/文案）"""
        return await page.evaluate("""
            () => {
                const result = {
                    title: '',
                    description: '',
                    images: [],
                    video: '',
                    author: '',
                };

                // 提取标题
                const titleEl = document.querySelector('#detail-title')
                              || document.querySelector('.title')
                              || document.querySelector('[class*="title"]');
                if (titleEl) result.title = titleEl.textContent.trim();

                // 提取文案描述
                const descEl = document.querySelector('#detail-desc')
                             || document.querySelector('.desc, .content, .note-text')
                             || document.querySelector('[class*="desc"]');
                if (descEl) result.description = descEl.textContent.trim();

                // 提取图片 URL（包含多种来源）
                const imgSelectors = [
                    '.swiper-slide img[src]',
                    '.carousel img[src]',
                    '.note-image img[src]',
                    '.media-container img[src]',
                    'img[class*="note"][src]',
                    '.slide-item img[src]',
                ];
                const imgSeen = new Set();
                for (const sel of imgSelectors) {
                    document.querySelectorAll(sel).forEach(img => {
                        let src = img.src || img.getAttribute('data-src') || '';
                        // 过滤掉头像等小图
                        if (src && !imgSeen.has(src) && !src.includes('avatar') 
                            && (src.includes('spectrum') || src.includes('ci.xiaohongshu') 
                                || src.includes('xhscdn') || src.includes('sns-img'))) {
                            imgSeen.add(src);
                            result.images.push(src);
                        }
                    });
                }

                // 提取视频 URL
                const videoEl = document.querySelector('video source[src]')
                              || document.querySelector('video[src]');
                if (videoEl) {
                    result.video = videoEl.src || videoEl.getAttribute('src') || '';
                }
                // 也尝试从 xgplayer 播放器提取
                if (!result.video) {
                    const xgVideo = document.querySelector('.xgplayer video');
                    if (xgVideo && xgVideo.src) result.video = xgVideo.src;
                }

                // 提取作者名
                const authorEl = document.querySelector('.author-name, .username, [class*="author"] .name');
                if (authorEl) result.author = authorEl.textContent.trim();

                return result;
            }
        """)

    async def _download_media(self, urls: List[str], save_dir: Path, title: str) -> int:
        """下载图片/视频文件"""
        downloaded = 0
        async with httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.xiaohongshu.com/"},
            timeout=30, follow_redirects=True,
        ) as client:
            for i, url in enumerate(urls):
                if not url:
                    continue
                # 确定文件扩展名
                ext = "jpg"
                if "video" in url or ".mp4" in url:
                    ext = "mp4"
                elif ".webp" in url:
                    ext = "webp"
                elif ".png" in url:
                    ext = "png"

                safe_title = re.sub(r'[\\/:*?"<>|]', '_', title)[:50]
                filename = f"{safe_title}_{i}.{ext}"
                filepath = save_dir / filename

                if filepath.exists():
                    downloaded += 1
                    continue

                try:
                    resp = await client.get(url)
                    if resp.status_code == 200 and len(resp.content) > 1000:
                        filepath.write_bytes(resp.content)
                        downloaded += 1
                        logger.info(f"[下载] ✓ 媒体文件: {filename} ({len(resp.content) // 1024}KB)")
                    else:
                        logger.warning(f"[下载] ✗ 媒体文件异常: HTTP {resp.status_code}, 大小 {len(resp.content)}")
                except Exception as e:
                    logger.warning(f"[下载] ✗ 媒体文件失败: {filename} — {e}")
        return downloaded

    async def check_and_download(self) -> int:
        """
        一体化检查 + 下载：在同一个 Playwright 浏览器会话中完成。
        1. 访问博主主页获取笔记列表
        2. 对比已知笔记，找出新帖
        3. 依次点击新帖卡片（触发 Vue 路由），从笔记详情页提取内容
        4. 下载图片/视频/文案
        5. 关闭弹窗后处理下一篇

        Returns:
            本次发现并处理的新笔记数量
        """
        logger.info(f"[检查] 开始检查博主: {self.user_id}")

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("[Playwright] 未安装，请运行: pip install playwright && playwright install chromium")
            return 0

        user_profile_url = f"https://www.xiaohongshu.com/user/profile/{self.user_id}"
        pw, browser, context = await self._create_browser_context()
        download_success = 0
        new_note_count = 0

        try:
            page = await context.new_page()
            logger.info(f"[浏览器] 启动 Chromium 检查博主 {self.user_id}...")

            await page.goto(user_profile_url, wait_until="domcontentloaded", timeout=40000)
            await page.wait_for_timeout(5000)

            # 滚动加载
            for _ in range(3):
                await page.evaluate("window.scrollBy(0, 800)")
                await asyncio.sleep(1.5)

            # 从 DOM 获取笔记列表
            card_infos = await self._get_note_ids_from_dom(page)
            logger.info(f"[DOM] 共发现 {len(card_infos)} 条笔记")

            if not card_infos:
                logger.warning("[检查] 未获取到任何笔记，可能是登录失效或博主无内容")
                # 截图调试
                debug_path = str(self.download_dir / f"debug_{self.user_id}.png")
                try:
                    await page.screenshot(path=debug_path, full_page=True)
                    logger.warning(f"[调试] 已保存页面截图: {debug_path}")
                except Exception:
                    pass
                return 0

            # 提取博主昵称
            try:
                name = await page.evaluate("""
                    () => {
                        const el = document.querySelector('.user-name, .username, [class*="nickname"]');
                        return el ? el.textContent.trim() : '';
                    }
                """)
                if name and not self.author_name:
                    self.author_name = name
            except Exception:
                pass

            # 过滤出新笔记
            all_note_ids = [c["note_id"] for c in card_infos]
            new_notes = [c for c in card_infos if c["note_id"] not in self._seen_ids]

            if not new_notes:
                logger.info(f"[检查] 无新笔记（已知 {len(self._seen_ids)} 篇）")
                return 0

            logger.info(f"[发现] 博主 {self.author_name or self.user_id} 有 {len(new_notes)} 篇新笔记！")

            # 首次运行：只记录基线
            if len(self._seen_ids) == 0:
                logger.info("[首次] 首次运行，记录当前所有笔记 ID 作为基线，不执行下载")
                for nid in all_note_ids:
                    self._seen_ids.add(nid)
                self._save_seen_ids()
                logger.info(f"[首次] 已记录 {len(self._seen_ids)} 篇笔记为基线")
                return 0

            new_note_count = len(new_notes)

            # ===== 逐个点击新笔记卡片，从详情页提取内容并下载 =====
            for idx, note_info in enumerate(new_notes, 1):
                note_id = note_info["note_id"]
                title = note_info.get("title", "")
                label = self.author_name or self.user_id

                logger.info(f"[处理 {idx}/{len(new_notes)}] 笔记 {note_id}: {title[:30]}")

                try:
                    # 确保在主页
                    if self.user_id not in page.url:
                        await page.goto(user_profile_url, wait_until="domcontentloaded", timeout=20000)
                        await page.wait_for_timeout(3000)

                    # 查找笔记卡片的容器元素（section.note-item 或外层 div）
                    # 注意：点击的是容器而不是 <a> 标签，这样才能触发 Vue 路由事件
                    card_el = await page.query_selector(
                        f'section.note-item:has(a[href*="{note_id}"])'
                    ) or await page.query_selector(
                        f'div.note-item:has(a[href*="{note_id}"])'
                    ) or await page.query_selector(
                        f'a[href*="{note_id}"]'
                    )

                    if not card_el:
                        logger.warning(f"[处理] 未找到笔记 {note_id} 的卡片元素")
                        self._seen_ids.add(note_id)
                        continue

                    # 滚动到可见位置并点击
                    await card_el.scroll_into_view_if_needed(timeout=5000)
                    await asyncio.sleep(0.5)
                    await card_el.click(timeout=10000)

                    # 等待笔记详情加载（URL 应该变为 /explore/{note_id}?xsec_token=...）
                    await asyncio.sleep(3)
                    current_url = page.url
                    logger.info(f"[处理] 导航后 URL: {current_url}")

                    # 提取笔记内容
                    content = await self._extract_note_content(page)

                    note_title = content.get("title", "") or title or note_id
                    note_desc = content.get("description", "")
                    note_images = content.get("images", [])
                    note_video = content.get("video", "")
                    note_author = content.get("author", "") or label

                    logger.info(
                        f"[提取] 标题: {note_title[:30]} | "
                        f"图片: {len(note_images)} | "
                        f"视频: {'✓' if note_video else '✗'} | "
                        f"文案: {len(note_desc)} 字"
                    )

                    # 准备下载目录
                    safe_author = re.sub(r'[\\/:*?"<>|]', '_', note_author)[:30]
                    safe_title = re.sub(r'[\\/:*?"<>|]', '_', note_title)[:50]
                    save_dir = self.download_dir / safe_author / f"{note_id}_{safe_title}"
                    save_dir.mkdir(parents=True, exist_ok=True)

                    # 保存文案
                    text_file = save_dir / f"{safe_title}.txt"
                    text_content = (
                        f"标题: {note_title}\n"
                        f"作者: {note_author}\n"
                        f"ID: {note_id}\n"
                        f"URL: {current_url}\n"
                        f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"\n{note_desc}"
                    )
                    text_file.write_text(text_content, encoding="utf-8")

                    # 下载媒体文件
                    media_urls = []
                    if note_video:
                        media_urls.append(note_video)
                    media_urls.extend(note_images)

                    if media_urls:
                        dl_count = await self._download_media(media_urls, save_dir, safe_title)
                        logger.info(f"[下载] 媒体下载完成: {dl_count}/{len(media_urls)}")
                    else:
                        logger.warning("[下载] 未提取到任何媒体文件 URL")

                    download_success += 1
                    logger.info(f"[下载] ✓ 成功: {note_title[:30]}")

                    # 推送通知
                    await self.notifier.push(
                        title=f"📕 {label} 发布新帖",
                        body=f"《{note_title}》\n{current_url}",
                        url=current_url,
                        group="小红书监控",
                    )

                except Exception as e:
                    logger.error(f"[处理] 笔记 {note_id} 处理异常: {e}")
                    import traceback
                    traceback.print_exc()

                # 无论成功与否都记录
                self._seen_ids.add(note_id)

                # 回到主页准备下一个
                try:
                    await page.goto(user_profile_url, wait_until="domcontentloaded", timeout=20000)
                    await page.wait_for_timeout(2000)
                except Exception:
                    pass

                if idx < len(new_notes):
                    await asyncio.sleep(2)

        except Exception as e:
            logger.error(f"[浏览器] 整体异常: {e}")
            import traceback
            traceback.print_exc()
        finally:
            try:
                await browser.close()
            except Exception:
                pass
            try:
                await pw.stop()
            except Exception:
                pass

        self._save_seen_ids()
        logger.info(
            f"[完成] 本轮新帖处理完毕: 共 {new_note_count} 篇，成功下载 {download_success} 篇"
        )
        return new_note_count


# ==========================================
# 多博主调度器
# ==========================================
class XHSMonitorScheduler:
    """
    多博主监控调度器，支持定时轮询。
    """

    def __init__(
            self,
            user_urls: List[str],
            interval: int = 600,
            download_dir: str = "downloads/xhs_monitor",
            cookie: str = "",
            bark_key: str = "",
            run_once: bool = False,
    ):
        """
        Args:
            user_urls: 博主主页 URL 列表
            interval: 轮询间隔（秒）
            download_dir: 下载根目录
            cookie: 小红书 Cookie
            bark_key: Bark Key
            run_once: True 则只运行一轮后退出
        """
        load_dotenv()

        self.user_urls = user_urls
        self.interval = interval
        self.run_once = run_once
        self.download_dir = Path(download_dir)

        # Cookie 优先级：参数 > .env
        self.cookie = cookie or os.getenv("XHS_COOKIE", "")

        # 创建统一的下载器（复用同一 XHS session）
        self.downloader = XHSDownloader(
            cookie=self.cookie,
            download_dir=str(self.download_dir),
            skip_existing=True,
            download_image=True,
            download_video=True,
        )

        # 创建 Bark 推送器
        self.notifier = BarkNotifier(bark_key=bark_key)

        # 已知笔记记录目录
        seen_file_dir = self.download_dir / ".seen"
        seen_file_dir.mkdir(parents=True, exist_ok=True)

        # 初始化每个博主的监控器
        self.monitors: List[XHSBloggerMonitor] = []
        for url in self.user_urls:
            if not USER_URL_PATTERN.search(url) and len(url) < 50:
                # 兼容直接传用户 ID 的情况
                url = f"https://www.xiaohongshu.com/user/profile/{url}"
            monitor = XHSBloggerMonitor(
                user_url=url,
                download_dir=str(self.download_dir),
                downloader=self.downloader,
                notifier=self.notifier,
                seen_file_dir=seen_file_dir,
                cookie=self.cookie,
            )
            self.monitors.append(monitor)

    async def run_round(self):
        """执行一轮所有博主的检查"""
        if not self.monitors:
            logger.warning("[调度] 没有配置任何博主，请检查 --users 参数或 XHS_MONITOR_USERS 环境变量")
            return

        for monitor in self.monitors:
            try:
                await monitor.check_and_download()
            except Exception as e:
                logger.error(f"[调度] 博主 {monitor.user_id} 检查异常: {e}")
                import traceback
                traceback.print_exc()
            # 多博主之间适当间隔
            if len(self.monitors) > 1:
                await asyncio.sleep(5)

    async def run(self):
        """启动监控主循环"""
        self._print_banner()

        if self.run_once:
            logger.info("[调度] 单次模式，执行一轮后退出")
            await self.run_round()
            logger.info("[调度] 单次检查完毕，程序退出")
            return

        # 持续循环
        round_num = 0
        while True:
            round_num += 1
            logger.info(f"\n{'=' * 60}")
            logger.info(f"  第 {round_num} 轮检查  |  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"{'=' * 60}")

            await self.run_round()

            logger.info(f"[调度] 本轮完成，{self.interval} 秒后进行下一轮检查...")
            logger.info(
                f"[调度] 下次检查时间: {datetime.fromtimestamp(time.time() + self.interval).strftime('%H:%M:%S')}"
            )

            try:
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                logger.info("[调度] 监控已停止")
                break

    def _print_banner(self):
        """打印启动信息"""
        print()
        print("=" * 60)
        print("  🔍 小红书博主新帖实时监控")
        print("=" * 60)
        print(f"  监控博主数: {len(self.monitors)}")
        for m in self.monitors:
            print(f"    - {m.user_id}")
        print(f"  检查间隔: {self.interval} 秒")
        print(f"  下载目录: {self.download_dir}")
        print(f"  Cookie:   {'✓ 已配置' if self.cookie else '✗ 未配置（可能影响效果）'}")
        print(f"  Bark:     {'✓ 已配置' if self.notifier.is_enabled() else '✗ 未配置（不会推送通知）'}")
        print(f"  模式:     {'单次' if self.run_once else '持续循环'}")
        print("=" * 60)
        print()


# ==========================================
# 命令行入口
# ==========================================

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="小红书博主新帖实时监控 — 发现新帖立即下载",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 使用 .env 配置的博主列表（XHS_MONITOR_USERS）
  python xhs_monitor.py

  # 手动指定单个博主
  python xhs_monitor.py --users "https://www.xiaohongshu.com/user/profile/xxx"

  # 监控多个博主（逗号分隔）
  python xhs_monitor.py --users "url1,url2,url3"

  # 每 5 分钟检查一次
  python xhs_monitor.py --interval 300

  # 仅检查一次，不循环
  python xhs_monitor.py --once

  # 指定下载目录
  python xhs_monitor.py --download-dir "D:/小红书下载"
        """,
    )

    parser.add_argument(
        "--users",
        type=str,
        default="",
        help="博主主页 URL 列表（逗号分隔），如不传则读取 .env 的 XHS_MONITOR_USERS",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=0,
        help="检查间隔（秒），如不传则读取 .env 的 XHS_MONITOR_INTERVAL（默认 600 秒）",
    )
    parser.add_argument(
        "--download-dir",
        type=str,
        default="",
        help="下载目录，如不传则读取 .env 的 XHS_MONITOR_DIR（默认 downloads/xhs_monitor）",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="只检查一次后退出（不循环）",
    )

    return parser.parse_args()


async def main():
    """主函数"""
    load_dotenv()
    args = parse_args()

    # 解析博主列表：命令行 > .env
    raw_users = args.users or os.getenv("XHS_MONITOR_USERS", "")
    user_urls = [u.strip() for u in raw_users.split(",") if u.strip()]

    # 降级：如果没有配置监控列表，尝试读取历史配置 XHS_TARGET_URL 作为单博主
    if not user_urls:
        fallback = os.getenv("XHS_TARGET_URL", "").strip()
        if fallback:
            logger.info(f"[配置] 未配置 XHS_MONITOR_USERS，使用 XHS_TARGET_URL 作为备选: {fallback}")
            user_urls = [fallback]
        else:
            logger.error("[配置] 请通过 --users 参数或 .env 的 XHS_MONITOR_USERS 指定要监控的博主")
            sys.exit(1)

    # 解析间隔
    interval = args.interval or int(os.getenv("XHS_MONITOR_INTERVAL", "600"))

    # 解析下载目录
    download_dir = args.download_dir or os.getenv("XHS_MONITOR_DIR", "downloads/xhs_monitor")

    scheduler = XHSMonitorScheduler(
        user_urls=user_urls,
        interval=interval,
        download_dir=download_dir,
        run_once=args.once,
    )

    try:
        await scheduler.run()
    except KeyboardInterrupt:
        print("\n\n[中断] 程序已被用户停止 (Ctrl+C)")


if __name__ == "__main__":
    asyncio.run(main())
