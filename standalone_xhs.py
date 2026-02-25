#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小红书用户历史笔记监控和批量下载脚本
功能: 监控指定用户的所有历史笔记，并批量下载内容
使用方式: python standalone_xhs.py --user-url <用户主页链接或用户ID>
"""
import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv
from XHS.xhs_downloader import XHSDownloader

# 添加 XHS 模块路径
sys.path.insert(0, str(Path(__file__).parent / "XHS"))



@dataclass
class UserNote:
    """用户笔记信息"""
    note_id: str
    note_url: str
    title: str
    note_type: str  # video 或 normal (图文)
    publish_time: Optional[str] = None
    likes: int = 0


class XHSUserMonitor:
    """
    小红书用户笔记监控器
    
    使用示例:
    ```python
    monitor = XHSUserMonitor(
        user_url="https://www.xiaohongshu.com/user/profile/xxx",
        download_dir="downloads"
    )
    await monitor.run()
    ```
    """

    # 用户主页 URL 正则
    USER_URL_PATTERN = re.compile(
        r"(?:https?://)?(?:www\.)?xiaohongshu\.com/user/profile/([a-zA-Z0-9_-]+)"
    )

    # 笔记链接正则
    NOTE_URL_PATTERN = re.compile(
        r"(?:https?://)?(?:www\.)?xiaohongshu\.com/(?:explore|discovery/item)/([a-zA-Z0-9]+)"
    )

    def __init__(
        self,
        user_url: str,
        download_dir: str = "downloads/xhs_user",
        delay: float = 3.0,
        max_notes: int = 0,
        cookie: str = None,
        user_agent: str = None,
        proxy: str = None,
        skip_existing: bool = True,
        save_text: bool = True,
        download_image: bool = True,
        download_video: bool = True,
    ):
        """
        初始化监控器
        
        Args:
            user_url: 用户主页链接或用户ID
            download_dir: 下载目录
            delay: 下载间隔时间(秒)，避免请求过快
            max_notes: 最大下载笔记数，0表示下载全部
            cookie: 小红书Cookie
            user_agent: User-Agent
            proxy: 代理地址
            skip_existing: 是否跳过已下载的笔记
            save_text: 是否保存文案
            download_image: 是否下载图片
            download_video: 是否下载视频
        """
        # 加载环境变量
        load_dotenv()

        self.user_url = user_url
        self.user_id = self._extract_user_id(user_url)
        self.download_dir = Path(download_dir)
        self.delay = delay
        self.max_notes = max_notes
        self.skip_existing = skip_existing
        self.save_text = save_text

        # 创建下载器
        self.downloader = XHSDownloader(
            cookie=cookie,
            user_agent=user_agent,
            proxy=proxy,
            download_dir=str(self.download_dir),
            download_image=download_image,
            download_video=download_video,
            skip_existing=skip_existing,
        )

        # 统计信息
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0,
        }

        # 笔记记录文件
        self.record_file = self.download_dir / f"user_{self.user_id}_notes.json"
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def _extract_user_id(self, url_or_id: str) -> str:
        """从URL中提取用户ID，或直接返回用户ID"""
        match = self.USER_URL_PATTERN.search(url_or_id)
        if match:
            return match.group(1)
        # 假设直接传入的就是用户ID
        return url_or_id.strip()

    def _is_user_profile_url(self) -> bool:
        """检测是否为完整的用户主页URL"""
        return bool(self.USER_URL_PATTERN.search(self.user_url))

    async def fetch_user_notes_from_page(self) -> List[UserNote]:
        """
        方案1: 从用户主页获取笔记列表 (使用 Playwright)
        策略: 边滚动边处理 —— 每次滚动后立即对当前可见的新笔记卡片执行 JS click，
               捕获新标签页 URL（含 xsec_token），避免虚拟滚动导致元素不可见。
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            print("[错误] 未安装 Playwright，请运行: pip install playwright && playwright install chromium")
            return []

        notes = []

        async with async_playwright() as p:
            print(f"[启动] 正在启动浏览器获取用户笔记列表...")
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(
                user_agent=self.downloader.user_agent or None
            )

            # 注入Cookie
            if self.downloader.cookie:
                cookies = []
                for item in self.downloader.cookie.split(';'):
                    if '=' in item:
                        name, value = item.strip().split('=', 1)
                        cookies.append({
                            'name': name,
                            'value': value,
                            'domain': '.xiaohongshu.com',
                            'path': '/'
                        })
                await context.add_cookies(cookies)

            page = await context.new_page()

            # 访问用户主页
            user_page_url = f"https://www.xiaohongshu.com/user/profile/{self.user_id}"
            print(f"[访问] {user_page_url}")
            await page.goto(user_page_url, wait_until='domcontentloaded')
            await asyncio.sleep(3)

            # ===== 边滚动边点击：每次滚动后立即处理当前可见的新笔记卡片 =====
            print("[开始] 边滚动边获取笔记 xsec_token...")
            processed_ids = set()
            no_change_rounds = 0
            scroll_round = 0

            while True:
                scroll_round += 1

                # 获取当前 DOM 中所有可见笔记链接
                card_infos = await page.evaluate('''() => {
                    const links = document.querySelectorAll('a[href*="/explore/"]');
                    const result = [];
                    links.forEach(link => {
                        const href = link.href || '';
                        const match = href.match(/\/explore\/([a-zA-Z0-9]+)/);
                        if (match) {
                            result.push({
                                note_id: match[1],
                                href: href,
                                title: (link.innerText || '').trim().slice(0, 50)
                            });
                        }
                    });
                    return result;
                }''')

                # 过滤出本轮新出现的卡片
                new_cards = [c for c in card_infos if c['note_id'] not in processed_ids]
                if not new_cards:
                    no_change_rounds += 1
                else:
                    no_change_rounds = 0

                # 处理新卡片：通过 JS 找到可见父元素坐标，用 page.mouse 中键点击
                for card in new_cards:
                    note_id = card['note_id']
                    if note_id in processed_ids:
                        continue
                    processed_ids.add(note_id)

                    print(f"  [{len(processed_ids)}] 处理笔记 {note_id}...")
                    title = card.get('title') or f"笔记_{note_id}"

                    try:
                        # JS 向上遍历 DOM，找到有宽高的可见父容器，返回其视口中心坐标
                        coords = await page.evaluate(f'''() => {{
                            const link = document.querySelector('a[href*="/explore/{note_id}"]');
                            if (!link) return null;
                            // 先检查 link 自身
                            let rect = link.getBoundingClientRect();
                            if (rect.width > 1 && rect.height > 1) {{
                                return {{x: rect.x + rect.width / 2, y: rect.y + rect.height / 2}};
                            }}
                            // 向上找最近的有宽高祖先
                            let el = link.parentElement;
                            for (let i = 0; i < 10; i++) {{
                                if (!el || el === document.body) break;
                                rect = el.getBoundingClientRect();
                                if (rect.width > 10 && rect.height > 10) {{
                                    return {{x: rect.x + rect.width / 2, y: rect.y + rect.height / 2}};
                                }}
                                el = el.parentElement;
                            }}
                            return null;
                        }}''')

                        if coords is None:
                            raise Exception("找不到可见父元素，卡片可能未在视口内")

                        # 用真实鼠标中键点击（打开新标签），完全绕过 Playwright 可见性检查
                        async with context.expect_page() as new_page_info:
                            await page.mouse.click(
                                coords['x'], coords['y'],
                                button='middle'
                            )

                        new_page = await new_page_info.value
                        await new_page.wait_for_load_state('domcontentloaded', timeout=10000)
                        final_url = new_page.url
                        await new_page.close()

                        # 从最终 URL 提取 xsec_token
                        token = None
                        if 'xsec_token=' in final_url:
                            token = final_url.split('xsec_token=')[1].split('&')[0]

                        if token:
                            note_url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={token}&xsec_source=pc_user"
                            print(f"    ✓ Token: {token[:20]}...")
                        else:
                            note_url = final_url or f"https://www.xiaohongshu.com/explore/{note_id}"
                            print(f"    ⚠️ 未获取到 Token (URL: {final_url[:80]})")

                        notes.append(UserNote(
                            note_id=note_id,
                            note_url=note_url,
                            title=title,
                            note_type="unknown"
                        ))

                    except Exception as e:
                        print(f"    ✗ 点击失败: {e}")
                        notes.append(UserNote(
                            note_id=note_id,
                            note_url=f"https://www.xiaohongshu.com/explore/{note_id}",
                            title=title,
                            note_type="unknown"
                        ))

                    # 点击间隔，防风控
                    await asyncio.sleep(max(0.5, self.delay * 0.3))

                    # 达到最大数量则停止
                    if self.max_notes > 0 and len(processed_ids) >= self.max_notes:
                        print(f"[完成] 已处理 {len(processed_ids)} 个，达到最大限制")
                        break

                # 检查是否达到最大数量
                if self.max_notes > 0 and len(processed_ids) >= self.max_notes:
                    break

                # 连续3次无新内容，判断已到底部
                if no_change_rounds >= 3:
                    print("[滚动完成] 连续3次无新笔记，已到底部")
                    break

                if scroll_round >= 30:
                    print("[滚动完成] 已达最大滚动次数")
                    break

                # 向下滚动，继续加载
                await page.evaluate('window.scrollBy(0, 800)')
                await asyncio.sleep(1.5)

            await browser.close()

        # 去重
        unique_notes = {}
        for note in notes:
            if note.note_id not in unique_notes:
                unique_notes[note.note_id] = note

        notes_with_token = sum(1 for n in unique_notes.values() if 'xsec_token' in n.note_url)
        print(f"[完成] 共获取 {len(unique_notes)} 个唯一笔记，其中 {notes_with_token} 个含 xsec_token")
        return list(unique_notes.values())

    async def fetch_user_notes_from_file(self, file_path: str) -> List[UserNote]:
        """
        方案2: 从文件读取笔记链接列表
        
        文件格式(每行一个链接):
        https://www.xiaohongshu.com/explore/xxx?xsec_token=xxx
        https://www.xiaohongshu.com/explore/yyy?xsec_token=yyy
        """
        notes = []

        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                match = self.NOTE_URL_PATTERN.search(line)
                if match:
                    note_id = match.group(1)
                    # 保留完整的原始URL（包含xsec_token等参数）
                    note_url = line
                    notes.append(UserNote(
                        note_id=note_id,
                        note_url=note_url,
                        title=f"笔记_{note_id}",
                        note_type="unknown"
                    ))

        print(f"[读取] 从文件读取到 {len(notes)} 个笔记链接")
        return notes

    async def fetch_user_notes_manual(self) -> List[UserNote]:
        """
        方案3: 手动输入笔记链接（交互式）
        """
        print("=" * 60)
        print("  手动输入笔记链接")
        print("=" * 60)
        print("请输入笔记链接，每行一个，输入空行结束:")
        print()

        notes = []
        while True:
            try:
                line = input("笔记链接: ").strip()
                if not line:
                    break

                match = self.NOTE_URL_PATTERN.search(line)
                if match:
                    note_id = match.group(1)
                    # 保留完整的原始URL（包含xsec_token等参数）
                    note_url = line
                    notes.append(UserNote(
                        note_id=note_id,
                        note_url=note_url,
                        title=f"笔记_{note_id}",
                        note_type="unknown"
                    ))
                    print(f"  ✓ 已添加: {note_id}")
                else:
                    print(f"  ✗ 无效链接，请重新输入")
            except (KeyboardInterrupt, EOFError):
                break

        print(f"\n[完成] 共添加 {len(notes)} 个笔记")
        return notes

    async def download_all_notes(self, notes: List[UserNote]):
        """批量下载所有笔记"""
        if not notes:
            print("[警告] 没有可下载的笔记")
            return

        self.stats['total'] = len(notes)

        print("\n" + "=" * 60)
        print(f"  开始批量下载 ({len(notes)} 个笔记)")
        print("=" * 60)
        print()

        for i, note in enumerate(notes, 1):
            print(f"\n[{i}/{len(notes)}] 下载笔记: {note.title}")
            print(f"  URL: {note.note_url}")

            try:
                # 检查是否已下载
                if self.skip_existing and self._is_downloaded(note.note_id):
                    print(f"  ⊙ 已下载，跳过")
                    self.stats['skipped'] += 1
                    continue

                # 下载笔记
                content = await self.downloader.download(
                    note.note_url,
                    save_text=self.save_text
                )

                if content:
                    print(f"  ✓ 下载成功")
                    self.stats['success'] += 1
                    self._mark_downloaded(note.note_id)
                else:
                    print(f"  ✗ 下载失败")
                    self.stats['failed'] += 1

            except Exception as e:
                print(f"  ✗ 下载异常: {e}")
                self.stats['failed'] += 1

            # 延迟，避免请求过快
            if i < len(notes):
                print(f"  ⏱ 等待 {self.delay} 秒...")
                await asyncio.sleep(self.delay)

        self._print_statistics()

    def _is_downloaded(self, note_id: str) -> bool:
        """检查笔记是否已下载"""
        if not self.record_file.exists():
            return False

        try:
            with open(self.record_file, 'r', encoding='utf-8') as f:
                records = json.load(f)
                return note_id in records.get('downloaded', [])
        except Exception:
            return False

    def _mark_downloaded(self, note_id: str):
        """标记笔记为已下载"""
        records = {'downloaded': [], 'updated_at': ''}

        if self.record_file.exists():
            try:
                with open(self.record_file, 'r', encoding='utf-8') as f:
                    records = json.load(f)
            except Exception:
                pass

        if note_id not in records['downloaded']:
            records['downloaded'].append(note_id)

        records['updated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(self.record_file, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    def _print_statistics(self):
        """打印下载统计"""
        print("\n" + "=" * 60)
        print("  下载统计")
        print("=" * 60)
        print(f"总计: {self.stats['total']}")
        print(f"成功: {self.stats['success']}")
        print(f"失败: {self.stats['failed']}")
        print(f"跳过: {self.stats['skipped']}")
        print("=" * 60)

    async def run(self, method: str = 'playwright'):
        """
        运行监控下载流程
        
        Args:
            method: 获取笔记的方法
                - 'playwright': 使用 Playwright 自动化浏览器
                - 'file': 从文件读取笔记链接
                - 'manual': 手动输入笔记链接
                - 'auto': 自动选择（推荐）
        """
        # 智能方法选择
        if method == 'auto' or (method == 'manual' and self._is_user_profile_url()):
            # 如果提供了完整的用户主页URL，自动使用playwright
            actual_method = 'playwright'
            print(f"[提示] 检测到用户主页URL，自动使用 Playwright 获取笔记列表")
        else:
            actual_method = method

        print("\n" + "=" * 60)
        print("  小红书用户历史笔记批量下载")
        print("=" * 60)
        print(f"用户ID: {self.user_id}")
        print(f"下载目录: {self.download_dir}")
        print(f"下载间隔: {self.delay} 秒")
        print(f"最大数量: {self.max_notes if self.max_notes > 0 else '全部'}")
        print(f"获取方式: {actual_method}")
        print("=" * 60)
        print()

        # 获取笔记列表
        if actual_method == 'playwright':
            notes = await self.fetch_user_notes_from_page()
        elif actual_method == 'file':
            file_path = input("请输入笔记链接文件路径: ").strip()
            notes = await self.fetch_user_notes_from_file(file_path)
        elif actual_method == 'manual':
            notes = await self.fetch_user_notes_manual()
        else:
            print(f"[错误] 不支持的方法: {actual_method}")
            return

        if not notes:
            print("[警告] 未获取到任何笔记")
            return

        # 批量下载
        await self.download_all_notes(notes)


# ==========================================
# 命令行入口
# ==========================================

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="小红书用户历史笔记监控和批量下载工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 使用 Playwright 自动获取笔记列表并下载
  python standalone_xhs.py --user-url "https://www.xiaohongshu.com/user/profile/xxx"
  
  # 从文件读取笔记链接
  python standalone_xhs.py --user-url "xxx" --method file
  
  # 手动输入笔记链接
  python standalone_xhs.py --user-url "xxx" --method manual
  
  # 限制下载数量
  python standalone_xhs.py --user-url "xxx" --max-notes 10
  
  # 设置下载间隔
  python standalone_xhs.py --user-url "xxx" --delay 5
        """
    )

    parser.add_argument(
        '--user-url',
        required=True,
        help='用户主页链接或用户ID'
    )
    parser.add_argument(
        '--method',
        choices=['auto', 'playwright', 'file', 'manual'],
        default='auto',
        help='获取笔记列表的方法 (默认: auto - 自动选择)'
    )
    parser.add_argument(
        '--download-dir',
        default='downloads/xhs_user',
        help='下载目录 (默认: downloads/xhs_user)'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=3.0,
        help='下载间隔时间(秒) (默认: 3.0)'
    )
    parser.add_argument(
        '--max-notes',
        type=int,
        default=0,
        help='最大下载笔记数，0表示全部 (默认: 0)'
    )
    parser.add_argument(
        '--no-skip-existing',
        action='store_true',
        help='不跳过已下载的笔记'
    )
    parser.add_argument(
        '--no-text',
        action='store_true',
        help='不保存文案'
    )
    parser.add_argument(
        '--no-image',
        action='store_true',
        help='不下载图片'
    )
    parser.add_argument(
        '--no-video',
        action='store_true',
        help='不下载视频'
    )

    return parser.parse_args()


async def main():
    """主函数"""
    args = parse_args()

    try:
        monitor = XHSUserMonitor(
            user_url=args.user_url,
            download_dir=args.download_dir,
            delay=args.delay,
            max_notes=args.max_notes,
            skip_existing=not args.no_skip_existing,
            save_text=not args.no_text,
            download_image=not args.no_image,
            download_video=not args.no_video,
        )

        await monitor.run(method=args.method)

    except KeyboardInterrupt:
        print("\n\n[中断] 程序被用户中断")
    except Exception as e:
        print(f"\n[错误] 程序运行出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
