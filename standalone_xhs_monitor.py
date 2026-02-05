# -*- coding: utf-8 -*-
"""
小红书博主监控独立脚本
用法:
    python standalone_xhs_monitor.py [选项]

选项:
    --login     强制重新登录
    --test      测试获取笔记
    --once      只执行一次检查
    --rewrite   批量改写未处理的笔记
    --stats     显示统计信息
    (无参数)    持续监控模式
"""

import os
import sys
import asyncio
import argparse
from pathlib import Path
from datetime import datetime

# 将项目根目录添加到 Python 路径
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

# 加载环境变量
from dotenv import load_dotenv, find_dotenv
env_file = find_dotenv()
if env_file:
    load_dotenv(env_file)


def get_logger():
    """获取日志记录器"""
    try:
        from Upload.utils.log import tencent_logger
        return tencent_logger
    except ImportError:
        import logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        return logging.getLogger(__name__)


logger = get_logger()


def print_banner():
    """打印启动横幅"""
    banner = """
╔═══════════════════════════════════════════════════════════════╗
║       📕 小红书博主监控工具 (XHS Monitor) v1.0.0              ║
║                                                               ║
║   功能: 监控指定博主发文，自动下载原图和内容                  ║
╚═══════════════════════════════════════════════════════════════╝
    """
    print(banner)


async def do_login(force: bool = False):
    """执行登录"""
    from XHS.xhs_auth import XHSAuth
    
    auth = XHSAuth(timeout=120)
    
    if force:
        logger.info("🔑 强制重新登录...")
    else:
        # 检查现有Cookie
        if await auth.validate_cookie():
            logger.success("✅ Cookie有效，无需重新登录")
            return True
        logger.info("🔑 Cookie无效或不存在，开始登录...")
    
    success = await auth.login(force=force)
    
    if success:
        logger.success("✅ 登录成功！")
    else:
        logger.error("❌ 登录失败")
    
    return success


async def do_test():
    """测试获取笔记"""
    from XHS.xhs_client import XHSClient
    
    # 获取配置的目标URL
    target_url = os.getenv('XHS_TARGET_URL')
    if not target_url:
        logger.error("❌ 请先配置 XHS_TARGET_URL 环境变量")
        return False
    
    logger.info(f"🔍 测试获取笔记: {target_url}")
    
    client = XHSClient()
    user_id = client.extract_user_id(target_url)
    
    if not user_id:
        logger.error(f"❌ 无法解析用户ID: {target_url}")
        return False
    
    logger.info(f"👤 用户ID: {user_id}")
    
    # 获取笔记列表
    notes = await client.get_user_notes(user_id, limit=5)
    
    if notes:
        logger.success(f"✅ 成功获取 {len(notes)} 条笔记:")
        print("-" * 60)
        for i, note in enumerate(notes, 1):
            print(f"{i}. [{note.note_id}] {note.title[:40] if note.title else '无标题'}...")
            print(f"   类型: {note.note_type} | 图片: {len(note.images)}张")
            print(f"   链接: {note.note_url}")
            print("-" * 60)
        
        # Test download of first note
        if len(notes) > 0:
            logger.info(f"📥 测试下载第一条笔记: {notes[0].note_id}")
            from XHS.xhs_downloader import XHSDownloader
            downloader = XHSDownloader()
            
            # Fetch detail first just like process_new_note does
            detail = await client.get_note_detail(notes[0].note_id)
            target_note = detail if detail else notes[0]
            
            result = await downloader.download_note(target_note)
            if result['success']:
                logger.success(f"✅ 下载成功: images={len(result['images'])}, video={result['video']}")
            else:
                logger.error(f"❌ 下载失败: {result}")
                
        return True
    else:
        logger.warning("⚠️ 未获取到任何笔记")
        return False


async def do_once():
    """执行一次监控检查"""
    # 获取配置
    target_url = os.getenv('XHS_TARGET_URL')
    if not target_url:
        logger.error("❌ 请先配置 XHS_TARGET_URL 环境变量")
        return
    
    interval = int(os.getenv('XHS_SCHEDULE_INTERVAL', os.getenv('SCHEDULE_INTERVAL', '10')))
    
    logger.info(f"📍 目标博主: {target_url}")
    
    # 先检查登录状态
    if not await do_login():
        logger.error("❌ 请先登录")
        return
    
    # 创建监控器
    from XHS.xhs_monitor import XHSMonitor
    
    monitor = XHSMonitor(target_url, check_interval=interval)
    
    # 执行一次检查
    processed = await monitor.run_once()
    
    if processed > 0:
        logger.success(f"✅ 本次处理了 {processed} 条新笔记")
    else:
        logger.info("📭 没有新笔记")
    
    # 显示统计
    stats = monitor.get_statistics()
    print(f"\n📊 统计信息: 总笔记 {stats.get('total_notes', 0)} | 已改写 {stats.get('rewritten_notes', 0)} | 已发布 {stats.get('published_notes', 0)}")


async def do_rewrite(limit: int = 10):
    """批量改写笔记"""
    from XHS.xhs_rewriter import XHSRewriter
    
    rewriter = XHSRewriter()
    count = rewriter.batch_rewrite(limit)
    
    logger.success(f"✅ 成功改写 {count} 条笔记")


def do_stats():
    """显示统计信息"""
    from XHS.xhs_storage import XHSStorage
    
    storage = XHSStorage()
    stats = storage.get_statistics()
    
    print("\n" + "=" * 50)
    print("📊 小红书监控统计")
    print("=" * 50)
    print(f"  📝 总笔记数:     {stats.get('total_notes', 0)}")
    print(f"  ✏️  已改写数:     {stats.get('rewritten_notes', 0)}")
    print(f"  📤 已发布数:     {stats.get('published_notes', 0)}")
    print(f"  👤 监控用户数:   {stats.get('monitored_users', 0)}")
    print("=" * 50 + "\n")


async def do_monitor():
    """持续监控模式"""
    # 获取配置
    target_url = os.getenv('XHS_TARGET_URL')
    if not target_url:
        logger.error("❌ 请先配置 XHS_TARGET_URL 环境变量")
        print("\n请在 .env 文件中添加:")
        print("  XHS_TARGET_URL=https://www.xiaohongshu.com/user/profile/你的目标用户ID")
        return
    
    interval = int(os.getenv('XHS_SCHEDULE_INTERVAL', os.getenv('SCHEDULE_INTERVAL', '10')))
    
    logger.info(f"📍 目标博主: {target_url}")
    logger.info(f"⏰ 检查间隔: {interval} 分钟")
    
    # 先检查登录状态
    if not await do_login():
        logger.error("❌ 请先登录，使用 --login 参数")
        return
    
    # 创建监控器
    from XHS.xhs_monitor import XHSMonitor
    
    monitor = XHSMonitor(target_url, check_interval=interval)
    
    # 开始持续监控
    logger.info("🚀 开始持续监控...")
    logger.info("💡 按 Ctrl+C 停止监控")
    
    try:
        await monitor.run_forever()
    except KeyboardInterrupt:
        logger.info("🛑 监控已停止")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="小红书博主监控工具",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--login', action='store_true', help='强制重新登录')
    parser.add_argument('--test', action='store_true', help='测试获取笔记')
    parser.add_argument('--once', action='store_true', help='只执行一次检查')
    parser.add_argument('--rewrite', type=int, nargs='?', const=10, metavar='N', 
                        help='批量改写笔记 (默认10条)')
    parser.add_argument('--stats', action='store_true', help='显示统计信息')
    
    args = parser.parse_args()
    
    # 打印横幅
    print_banner()
    
    print(f"⏰ 启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 60)
    
    # 根据参数执行不同操作
    if args.login:
        asyncio.run(do_login(force=True))
    elif args.test:
        asyncio.run(do_test())
    elif args.once:
        asyncio.run(do_once())
    elif args.rewrite is not None:
        asyncio.run(do_rewrite(args.rewrite))
    elif args.stats:
        do_stats()
    else:
        # 默认：持续监控
        asyncio.run(do_monitor())


if __name__ == "__main__":
    main()
