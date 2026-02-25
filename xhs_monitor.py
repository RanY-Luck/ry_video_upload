#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小红书用户笔记实时监控脚本
功能: 定期检查用户是否发布新笔记，自动下载
使用方式: python xhs_monitor.py --user-url <用户主页链接或用户ID>
"""
import argparse
import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Set, Optional
from dotenv import load_dotenv

# 添加 XHS 模块路径
sys.path.insert(0, str(Path(__file__).parent / "XHS"))

from XHS.xhs_downloader import XHSDownloader


class XHSUserMonitor:
    """
    小红书用户笔记实时监控器
    
    定期检查用户是否发布新笔记，自动下载新内容
    """
    
    # 用户主页 URL 正则
    USER_URL_PATTERN = re.compile(
        r"(?:https?://)?(?:www\.)?xiaohongshu\.com/user/profile/([a-zA-Z0-9_-]+)"
    )
    
    def __init__(
        self,
        user_url: str,
        download_dir: str = "downloads/xhs_monitor",
        check_interval: int = 300,  # 5分钟
        cookie: str = None,
        user_agent: str = None,
        proxy: str = None,
        save_text: bool = True,
        download_image: bool = True,
        download_video: bool = True,
    ):
        """
        初始化监控器
        
        Args:
            user_url: 用户主页链接或用户ID
            download_dir: 下载目录
            check_interval: 检查间隔时间(秒)，默认300秒（5分钟）
            cookie: 小红书Cookie
            user_agent: User-Agent
            proxy: 代理地址
            save_text: 是否保存文案
            download_image: 是否下载图片
            download_video: 是否下载视频
        """
        # 加载环境变量
        load_dotenv()
        
        self.user_url = user_url
        self.user_id = self._extract_user_id(user_url)
        self.download_dir = Path(download_dir) / f"user_{self.user_id}"
        self.check_interval = check_interval
        self.save_text = save_text
        
        # 创建下载器
        self.downloader = XHSDownloader(
            cookie=cookie,
            user_agent=user_agent,
            proxy=proxy,
            download_dir=str(self.download_dir),
            download_image=download_image,
            download_video=download_video,
            skip_existing=True,  # 监控模式下总是跳过已下载的
        )
        
        # 监控状态文件
        self.state_file = self.download_dir / "monitor_state.json"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        
        # 加载已知笔记列表
        self.known_notes = self._load_known_notes()
        
        # 统计信息
        self.stats = {
            'total_checks': 0,
            'new_notes_found': 0,
            'download_success': 0,
            'download_failed': 0,
        }
    
    def _extract_user_id(self, url_or_id: str) -> str:
        """从URL中提取用户ID，或直接返回用户ID"""
        match = self.USER_URL_PATTERN.search(url_or_id)
        if match:
            return match.group(1)
        return url_or_id.strip()
    
    def _load_known_notes(self) -> Set[str]:
        """加载已知的笔记ID列表"""
        if not self.state_file.exists():
            return set()
        
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
                return set(state.get('known_notes', []))
        except Exception as e:
            print(f"[警告] 加载监控状态失败: {e}")
            return set()
    
    def _save_known_notes(self):
        """保存已知的笔记ID列表"""
        state = {
            'user_id': self.user_id,
            'known_notes': list(self.known_notes),
            'last_check': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'stats': self.stats,
        }
        
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    
    async def get_latest_notes_from_file(self, notes_file: str) -> List[str]:
        """
        从文件读取最新的笔记链接列表
        
        用户需要定期更新这个文件（通过浏览器控制台脚本）
        """
        if not Path(notes_file).exists():
            print(f"[错误] 笔记链接文件不存在: {notes_file}")
            return []
        
        notes = []
        note_pattern = re.compile(r'/explore/([a-zA-Z0-9]+)')
        
        with open(notes_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # 提取笔记ID
                match = note_pattern.search(line)
                if match:
                    notes.append(line)  # 保存完整URL
        
        return notes
    
    async def get_latest_notes_interactive(self) -> List[str]:
        """
        交互式获取最新笔记
        
        提示用户在浏览器中运行提取脚本，然后粘贴结果
        """
        print("\n" + "=" * 60)
        print("  获取最新笔记")
        print("=" * 60)
        print("请在浏览器中:")
        print("1. 打开用户主页并刷新")
        print("2. 按F12打开控制台")
        print("3. 运行 extract_xhs_links.js 脚本")
        print("4. 将输出的链接粘贴到下面（每行一个，输入空行结束）")
        print("=" * 60)
        print()
        
        notes = []
        note_pattern = re.compile(r'/explore/([a-zA-Z0-9]+)')
        
        while True:
            try:
                line = input("笔记链接: ").strip()
                if not line:
                    break
                
                match = note_pattern.search(line)
                if match:
                    notes.append(line)
                else:
                    print(f"  ✗ 无效链接")
            except (KeyboardInterrupt, EOFError):
                break
        
        return notes
    
    async def check_new_notes(self, notes_file: Optional[str] = None) -> List[str]:
        """
        检查是否有新笔记
        
        Args:
            notes_file: 笔记链接文件路径，如果为None则使用交互式方式
        
        Returns:
            新笔记的URL列表
        """
        # 获取最新笔记列表
        if notes_file:
            latest_notes = await self.get_latest_notes_from_file(notes_file)
        else:
            latest_notes = await self.get_latest_notes_interactive()
        
        if not latest_notes:
            return []
        
        # 提取笔记ID
        note_pattern = re.compile(r'/explore/([a-zA-Z0-9]+)')
        new_notes = []
        
        for note_url in latest_notes:
            match = note_pattern.search(note_url)
            if match:
                note_id = match.group(1)
                if note_id not in self.known_notes:
                    new_notes.append(note_url)
                    self.known_notes.add(note_id)
        
        return new_notes
    
    async def download_new_notes(self, new_notes: List[str]):
        """下载新笔记"""
        if not new_notes:
            return
        
        print(f"\n[发现] 找到 {len(new_notes)} 个新笔记，开始下载...")
        
        for i, note_url in enumerate(new_notes, 1):
            print(f"\n[{i}/{len(new_notes)}] 下载: {note_url[:80]}...")
            
            try:
                content = await self.downloader.download(
                    note_url,
                    save_text=self.save_text
                )
                
                if content:
                    print(f"  ✓ 下载成功")
                    self.stats['download_success'] += 1
                else:
                    print(f"  ✗ 下载失败")
                    self.stats['download_failed'] += 1
            except Exception as e:
                print(f"  ✗ 下载异常: {e}")
                self.stats['download_failed'] += 1
            
            # 延迟
            if i < len(new_notes):
                await asyncio.sleep(2)
    
    async def run_once(self, notes_file: Optional[str] = None):
        """运行一次检查"""
        self.stats['total_checks'] += 1
        
        print(f"\n{'='*60}")
        print(f"  检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  检查次数: {self.stats['total_checks']}")
        print(f"{'='*60}")
        
        # 检查新笔记
        new_notes = await self.check_new_notes(notes_file)
        
        if new_notes:
            self.stats['new_notes_found'] += len(new_notes)
            print(f"[新笔记] 发现 {len(new_notes)} 个新笔记！")
            
            # 下载新笔记
            await self.download_new_notes(new_notes)
        else:
            print("[无更新] 没有发现新笔记")
        
        # 保存状态
        self._save_known_notes()
    
    async def run_monitor(self, notes_file: Optional[str] = None, max_checks: int = 0):
        """
        运行持续监控
        
        Args:
            notes_file: 笔记链接文件路径
            max_checks: 最大检查次数，0表示无限次
        """
        print("\n" + "=" * 60)
        print("  小红书用户笔记监控")
        print("=" * 60)
        print(f"用户ID: {self.user_id}")
        print(f"检查间隔: {self.check_interval} 秒 ({self.check_interval//60} 分钟)")
        print(f"下载目录: {self.download_dir}")
        print(f"已知笔记: {len(self.known_notes)} 个")
        print("=" * 60)
        print()
        
        if notes_file:
            print(f"[模式] 文件监控模式")
            print(f"[文件] {notes_file}")
            print(f"[提示] 请定期运行浏览器脚本更新此文件")
        else:
            print(f"[模式] 交互式监控模式")
            print(f"[提示] 每次检查时需要手动粘贴最新链接")
        
        print(f"\n按 Ctrl+C 停止监控\n")
        
        check_count = 0
        
        try:
            while True:
                # 运行一次检查
                await self.run_once(notes_file)
                
                check_count += 1
                if max_checks > 0 and check_count >= max_checks:
                    print(f"\n[完成] 已达到最大检查次数 {max_checks}")
                    break
                
                # 等待下次检查
                print(f"\n[等待] {self.check_interval} 秒后进行下次检查...")
                await asyncio.sleep(self.check_interval)
                
        except KeyboardInterrupt:
            print("\n\n[停止] 监控已停止")
        
        self._print_statistics()
    
    def _print_statistics(self):
        """打印统计信息"""
        print("\n" + "=" * 60)
        print("  监控统计")
        print("=" * 60)
        print(f"总检查次数: {self.stats['total_checks']}")
        print(f"发现新笔记: {self.stats['new_notes_found']}")
        print(f"下载成功: {self.stats['download_success']}")
        print(f"下载失败: {self.stats['download_failed']}")
        print(f"已知笔记总数: {len(self.known_notes)}")
        print("=" * 60)


# ==========================================
# 命令行入口
# ==========================================

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="小红书用户笔记实时监控工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 交互式监控（每5分钟检查一次）
  python xhs_monitor.py --user-url "用户ID"
  
  # 文件监控模式（从文件读取最新链接）
  python xhs_monitor.py --user-url "用户ID" --notes-file "xhs_links.txt"
  
  # 自定义检查间隔（10分钟）
  python xhs_monitor.py --user-url "用户ID" --interval 600
  
  # 只检查一次（不持续监控）
  python xhs_monitor.py --user-url "用户ID" --once
        """
    )
    
    parser.add_argument(
        '--user-url',
        required=True,
        help='用户主页链接或用户ID'
    )
    parser.add_argument(
        '--notes-file',
        help='笔记链接文件路径（需要定期更新）'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=300,
        help='检查间隔时间(秒) (默认: 300，即5分钟)'
    )
    parser.add_argument(
        '--download-dir',
        default='downloads/xhs_monitor',
        help='下载目录 (默认: downloads/xhs_monitor)'
    )
    parser.add_argument(
        '--once',
        action='store_true',
        help='只检查一次，不持续监控'
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
            check_interval=args.interval,
            save_text=not args.no_text,
            download_image=not args.no_image,
            download_video=not args.no_video,
        )
        
        if args.once:
            # 只检查一次
            await monitor.run_once(args.notes_file)
        else:
            # 持续监控
            await monitor.run_monitor(args.notes_file)
        
    except KeyboardInterrupt:
        print("\n\n[中断] 程序被用户中断")
    except Exception as e:
        print(f"\n[错误] 程序运行出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
