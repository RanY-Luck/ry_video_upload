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

    async def fetch_latest_notes(self) -> List[Dict]:
        """
        使用 Playwright 访问博主主页，通过 DOM 解析 + __INITIAL_STATE__ 提取笔记列表。
        （不再依赖 API 拦截，因为小红书安全盾会阻止 user_posted API 的发起）

        Returns:
            笔记信息列表，每项包含 note_id, title, xsec_token, note_url
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("[Playwright] 未安装 Playwright，请运行: pip install playwright && playwright install chromium")
            return []

        captured: Dict[str, Dict] = {}
        page_user_name = ""

        user_profile_url = f"https://www.xiaohongshu.com/user/profile/{self.user_id}"

        async with async_playwright() as p:
            logger.info(f"[浏览器] 启动 Chromium 检查博主 {self.user_id}...")

            browser = await p.chromium.launch(
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

            # 注入反检测脚本（隐藏 webdriver 标记）
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
            else:
                logger.warning("[浏览器] 未配置 Cookie，可能无法获取笔记数据")

            page = await context.new_page()

            try:
                await page.goto(user_profile_url, wait_until="domcontentloaded", timeout=40000)
                # 等待页面渲染完成
                await page.wait_for_timeout(5000)

                # 向下滚动以加载更多笔记卡片
                for _ in range(3):
                    await page.evaluate("window.scrollBy(0, 800)")
                    await asyncio.sleep(1.5)

                # ===== 策略1：从 __INITIAL_STATE__ 提取 SSR 预渲染数据 =====
                try:
                    initial_state = await page.evaluate("""
                        () => {
                            try {
                                const state = window.__INITIAL_STATE__;
                                if (!state) return null;
                                // Playwright 需要返回可序列化对象，这里直接提取核心字段
                                const result = {user: {}, notes: []};

                                // 提取用户信息
                                if (state.user && state.user.userPageData) {
                                    const u = state.user.userPageData;
                                    result.user = {nickname: u.basicInfo?.nickname || ''};
                                    // 提取用户发布的笔记
                                    const notes = u.notes || [];
                                    for (const n of notes) {
                                        if (n.id || n.noteId) {
                                            result.notes.push({
                                                note_id: n.id || n.noteId || '',
                                                title: n.displayTitle || n.title || '',
                                                xsec_token: n.xsecToken || '',
                                            });
                                        }
                                    }
                                }

                                // 尝试从 feed 路径读取
                                if (result.notes.length === 0 && state.feed) {
                                    const feeds = Object.values(state.feed);
                                    for (const feed of feeds) {
                                        if (feed && Array.isArray(feed.items)) {
                                            for (const item of feed.items) {
                                                const nc = item.noteCard || item;
                                                const nid = nc.id || nc.noteId || item.id || '';
                                                if (nid) {
                                                    result.notes.push({
                                                        note_id: nid,
                                                        title: nc.displayTitle || nc.title || '',
                                                        xsec_token: nc.xsecToken || '',
                                                    });
                                                }
                                            }
                                        }
                                    }
                                }

                                return result;
                            } catch(e) {
                                return {error: e.toString()};
                            }
                        }
                    """)

                    if initial_state and not initial_state.get("error"):
                        nickname = initial_state.get("user", {}).get("nickname", "")
                        if nickname and not page_user_name:
                            page_user_name = nickname

                        ssr_notes = initial_state.get("notes", [])
                        if ssr_notes:
                            logger.info(f"[SSR] 从 __INITIAL_STATE__ 提取到 {len(ssr_notes)} 条笔记")
                        for n in ssr_notes:
                            nid = n.get("note_id", "")
                            if nid and nid not in captured:
                                captured[nid] = n
                    elif initial_state and initial_state.get("error"):
                        logger.warning(f"[SSR] __INITIAL_STATE__ 解析异常: {initial_state['error']}")
                    else:
                        logger.info("[SSR] __INITIAL_STATE__ 为空或不存在")
                except Exception as e:
                    logger.warning(f"[SSR] 提取 __INITIAL_STATE__ 失败: {e}")

                # ===== 策略2：从 DOM 页面元素提取笔记链接 =====
                try:
                    dom_notes = await page.evaluate("""
                        () => {
                            const results = [];
                            // 查找所有笔记卡片链接（多种选择器兼容）
                            const selectors = [
                                'a[href*="/explore/"]',
                                'a[href*="/discovery/item/"]',
                                'a[href*="xsec_token"]',
                                'section.note-item a',
                                'div.note-item a',
                                '.feeds-container a[href*="/explore/"]',
                            ];
                            const seen = new Set();
                            for (const sel of selectors) {
                                const links = document.querySelectorAll(sel);
                                for (const a of links) {
                                    const href = a.href || a.getAttribute('href') || '';
                                    // 从 href 提取 note_id
                                    const m = href.match(/\\/explore\\/([a-f0-9]+)/i)
                                             || href.match(/\\/discovery\\/item\\/([a-f0-9]+)/i);
                                    if (!m) continue;
                                    const noteId = m[1];
                                    if (seen.has(noteId)) continue;
                                    seen.add(noteId);

                                    // 提取 xsec_token
                                    const tokenMatch = href.match(/xsec_token=([^&]+)/);
                                    const token = tokenMatch ? decodeURIComponent(tokenMatch[1]) : '';

                                    // 提取标题（从卡片文字元素）
                                    const titleEl = a.querySelector('.title, .note-title, span, footer span');
                                    const title = (titleEl ? titleEl.textContent : '') || a.textContent || '';

                                    results.push({
                                        note_id: noteId,
                                        title: title.trim().substring(0, 100),
                                        xsec_token: token,
                                    });
                                }
                            }
                            return results;
                        }
                    """)

                    if dom_notes:
                        logger.info(f"[DOM] 从页面 DOM 提取到 {len(dom_notes)} 条笔记链接")
                        for n in dom_notes:
                            nid = n.get("note_id", "")
                            token = n.get("xsec_token", "")
                            # 补充或更新（优先保留有 token 的）
                            if nid and (nid not in captured or (token and not captured[nid].get("xsec_token"))):
                                captured[nid] = n
                    else:
                        logger.warning("[DOM] 未从 DOM 中找到任何笔记链接")

                except Exception as e:
                    logger.warning(f"[DOM] DOM 提取异常: {e}")

                # ===== 策略3：打印页面截图路径供人工排查 =====
                if not captured:
                    debug_path = str(self.download_dir / f"debug_{self.user_id}.png")
                    try:
                        await page.screenshot(path=debug_path, full_page=True)
                        logger.warning(f"[调试] 未获取到笔记，已保存页面截图: {debug_path}")
                    except Exception:
                        pass

                    # 打印页面 URL 和标题，确认是否跳转
                    current_url = page.url
                    page_title = await page.title()
                    logger.info(f"[调试] 当前页面 URL: {current_url}")
                    logger.info(f"[调试] 当前页面标题: {page_title}")

            except Exception as e:
                logger.warning(f"[浏览器] 页面加载异常: {e}")
            finally:
                await browser.close()

        if page_user_name and not self.author_name:
            self.author_name = page_user_name

        # 构建最终笔记列表（带完整 URL）
        notes = []
        for note_data in captured.values():
            note_id = note_data["note_id"]
            token = note_data.get("xsec_token", "")
            if token:
                note_url = (
                    f"https://www.xiaohongshu.com/explore/{note_id}"
                    f"?xsec_token={token}&xsec_source=pc_user"
                )
            else:
                note_url = f"https://www.xiaohongshu.com/explore/{note_id}"
            notes.append({
                "note_id": note_id,
                "title": note_data.get("title", ""),
                "xsec_token": token,
                "note_url": note_url,
            })

        logger.info(f"[API] 共捕获 {len(notes)} 个笔记（博主: {self.user_id}）")
        return notes

    async def check_and_download(self) -> int:
        """
        执行一次检查：抓取最新笔记 → 对比 → 下载新帖。

        Returns:
            本次发现并处理的新笔记数量
        """
        logger.info(f"[检查] 开始检查博主: {self.user_id}")
        latest_notes = await self.fetch_latest_notes()

        if not latest_notes:
            logger.warning(f"[检查] 未获取到任何笔记，可能是登录失效或博主无内容")
            return 0

        # 找出新笔记（当前记录不含的）
        new_notes = [n for n in latest_notes if n["note_id"] not in self._seen_ids]

        if not new_notes:
            logger.info(f"[检查] 无新笔记（已知 {len(self._seen_ids)} 篇）")
            return 0

        logger.info(f"[发现] 博主 {self.author_name or self.user_id} 有 {len(new_notes)} 篇新笔记！")

        # 首次运行时只记录 ID，不下载（防止把所有历史帖都下载一遍）
        if len(self._seen_ids) == 0:
            logger.info("[首次] 首次运行，记录当前所有笔记 ID 作为基线，不执行下载")
            for note in latest_notes:
                self._seen_ids.add(note["note_id"])
            self._save_seen_ids()
            logger.info(f"[首次] 已记录 {len(self._seen_ids)} 篇笔记为基线，后续检测到新帖才会下载")
            return 0

        # 下载新笔记
        download_success = 0
        for idx, note in enumerate(new_notes, 1):
            note_id = note["note_id"]
            note_url = note["note_url"]
            title = note["title"]
            label = self.author_name or self.user_id

            logger.info(f"[下载 {idx}/{len(new_notes)}] {title} — {note_url}")

            try:
                content = await self.downloader.download(note_url, save_text=True)
                if content:
                    logger.info(f"[下载] ✓ 成功: {title}")
                    download_success += 1

                    # Bark 推送通知
                    await self.notifier.push(
                        title=f"📕 {label} 发布新帖",
                        body=f"《{title}》\n{note_url}",
                        url=note_url,
                        group="小红书监控",
                    )
                else:
                    logger.warning(f"[下载] ✗ 失败: {title}")
            except Exception as e:
                logger.error(f"[下载] 异常: {title} — {e}")

            # 无论成功与否都记录（避免重复尝试）
            self._seen_ids.add(note_id)

            # 下载间隔，避免请求过快
            if idx < len(new_notes):
                await asyncio.sleep(3)

        self._save_seen_ids()
        logger.info(
            f"[完成] 本轮新帖处理完毕: 共 {len(new_notes)} 篇，成功下载 {download_success} 篇"
        )
        return len(new_notes)


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
