#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小红书内容下载器
功能: 下载小红书笔记的文案、视频或图片
使用方式: 传入笔记链接，自动下载内容到指定目录
"""
import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
from XHS.source import XHS
from XHS.source.expansion import Namespace
from XHS.source.application.request import Html
from XHS.source.application.video import Video
# 添加 source 模块路径
sys.path.insert(0, str(Path(__file__).parent))



# ==========================================
# Monkey Patch: 增强无水印视频提取逻辑
# ==========================================
def generate_video_link_patched(cls, data: Namespace) -> list:
    """增强版无水印视频链接生成"""
    # 1. 尝试直接获取 originVideoKey
    if t := data.safe_extract(".".join(cls.VIDEO_LINK)):
        return [Html.format_url(f"https://sns-video-bd.xhscdn.com/{t}")]
    
    # 2. 尝试从 masterUrl 提取
    try:
        items = cls.get_video_items(data)
        if items:
            master_url = items[0].masterUrl
            
            # 匹配 1: /stream/{key}/
            if "/stream/" in master_url:
                parts = master_url.split("/stream/")
                if len(parts) > 1:
                    key_part = parts[1].split("/")[0]
                    if len(key_part) > 10:
                        return [Html.format_url(f"https://sns-video-bd.xhscdn.com/{key_part}")]
            
            # 匹配 2: 就是 key 本身
            elif master_url.count("/") == 3:
                key_part = master_url.split("/")[-1]
                if len(key_part) > 20:
                    return [Html.format_url(f"https://sns-video-bd.xhscdn.com/{key_part}")]
                    
    except Exception:
        pass
        
    return []

# 应用 Patch
Video.generate_video_link = classmethod(generate_video_link_patched)


@dataclass
class XHSContent:
    """小红书内容数据类"""
    note_id: str                          # 笔记ID
    title: str                            # 标题
    description: str                      # 文案/描述
    tags: str                             # 标签
    content_type: str                     # 内容类型 (视频/图文)
    publish_time: str                     # 发布时间
    author_name: str                      # 作者昵称
    author_id: str                        # 作者ID
    likes: int                            # 点赞数
    collects: int                         # 收藏数
    comments: int                         # 评论数
    shares: int                           # 分享数
    note_url: str                         # 笔记链接
    download_urls: List[str]              # 下载链接列表 (视频或图片)
    download_path: Optional[Path] = None  # 下载保存路径


class XHSDownloader:
    """
    小红书内容下载器
    
    使用示例:
    ```python
    # 方式1: 使用默认配置 (从.env读取)
    downloader = XHSDownloader()
    content = await downloader.download("https://www.xiaohongshu.com/explore/xxx")
    
    # 方式2: 自定义配置
    downloader = XHSDownloader(
        cookie="your_cookie",
        download_dir="./downloads"
    )
    content = await downloader.download("https://xhslink.com/xxx")
    
    # 只获取信息不下载
    content = await downloader.get_info("https://www.xiaohongshu.com/explore/xxx")
    ```
    """

    def __init__(
        self,
        cookie: str = None,
        user_agent: str = None,
        proxy: str = None,
        download_dir: str = "downloads",
        timeout: int = 10,
        max_retry: int = 3,
        download_image: bool = True,
        download_video: bool = True,
        skip_existing: bool = False,
    ):
        """
        初始化下载器
        
        Args:
            cookie: 小红书 Cookie，如不传则从 .env 的 XHS_COOKIE 读取
            user_agent: User-Agent，如不传则从 .env 的 XHS_USER_AGENT 读取
            proxy: 代理地址，如不传则从 .env 的 XHS_PROXY 读取
            download_dir: 下载目录
            timeout: 请求超时时间(秒)
            max_retry: 最大重试次数
            download_image: 是否下载图片
            download_video: 是否下载视频
            skip_existing: 是否跳过已下载的内容，默认为 False (会重新下载)
        """
        # 加载环境变量
        load_dotenv()
        
        # 从 .env 读取配置，参数传入优先
        self.cookie = cookie or os.getenv("XHS_COOKIE", "")
        self.user_agent = user_agent or os.getenv("XHS_USER_AGENT", "")
        self.proxy = proxy or os.getenv("XHS_PROXY", None)
        
        self.download_dir = Path(download_dir)
        self.timeout = timeout
        self.max_retry = max_retry
        self.download_image = download_image
        self.download_video = download_video
        self.skip_existing = skip_existing
        
        # 创建下载目录
        self.download_dir.mkdir(parents=True, exist_ok=True)
        
        # 验证 Cookie
        if not self.cookie:
            print("[警告] 未配置 XHS_COOKIE，可能无法正常下载内容")
            
    async def download_note(self, note, save_text: bool = True):
        """
        下载 XHSNote 对象
        Compatibility method for XHSMonitor
        """
        if not hasattr(note, 'note_url') or not note.note_url:
            print(f"[错误] 笔记对象缺失 URL: {note}")
            return {'success': False, 'images': [], 'video': None}
            
        print(f"[开始] 下载笔记: {note.note_url}")
        
        # Try standard download first
        content = await self.download(note.note_url, save_text=save_text)
        
        # Fallback if standard download failed but we have data in note object
        if not content and hasattr(note, 'images') and note.images:
            print("[警告] 标准下载失败，尝试使用现有数据下载 (可能缺失视频/详细文案)...")
            content = await self.download_manual(note, save_text)

        if content:
            return {
                'success': True,
                'images': content.download_urls, 
                'video': None # Video not supported in manual mode reliably yet
            }
        else:
             return {'success': False, 'images': [], 'video': None}

    async def download_manual(self, note, save_text: bool = True) -> Optional[XHSContent]:
        """使用笔记对象中的现有数据进行下载 (Fallback)"""
        try:
            # Construct minimal XHSContent
            # Clean title
            import re
            safe_title = self._clean_filename(note.title)
            
            content = XHSContent(
                note_id=note.note_id,
                title=note.title,
                description="(标准抓取失败，仅含标题/图片)",
                tags="",
                content_type=note.note_type,
                publish_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), # Unknown time
                author_name="Unknown", # Should ideally pass this in note object
                author_id="Unknown",
                likes=0,
                collects=0,
                comments=0,
                shares=0,
                note_url=note.note_url,
                download_urls=note.images,
                download_path=None
            )
            
            # Setup path
            author_folder = f"Manual_{safe_title[:10]}"
            save_dir = self.download_dir / author_folder
            save_dir.mkdir(parents=True, exist_ok=True)
            content.download_path = save_dir
            
            # Download images using httpx directly
            import httpx
            async with httpx.AsyncClient(headers={'User-Agent': self.user_agent}) as client:
                downloaded_files = []
                for i, url in enumerate(content.download_urls):
                    if not url: continue
                    ext = "jpg" # Default
                    if "webp" in url: ext = "webp"
                    
                    filename = f"{safe_title[:30]}_{i}.{ext}"
                    filepath = save_dir / filename
                    
                    if filepath.exists() and self.skip_existing:
                        downloaded_files.append(str(filepath))
                        continue
                        
                    print(f"Downloading image: {url[:50]}...")
                    try:
                        resp = await client.get(url, timeout=30)
                        if resp.status_code == 200:
                            filepath.write_bytes(resp.content)
                            downloaded_files.append(str(filepath))
                    except Exception as e:
                        print(f"Image download failed: {e}")
            
            # Save text
            if save_text:
                text_file = save_dir / f"{safe_title}.txt"
                text_content = f"Title: {content.title}\nID: {content.note_id}\nURL: {content.note_url}\n\n(Downloaded via Manual Fallback)"
                text_file.write_text(text_content, encoding='utf-8')
                
            print(f"[成功] 手动下载完成: {content.title[:30]}...")
            return content
            
        except Exception as e:
            print(f"Manual download failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def download(
        self,
        url: str,
        save_text: bool = True,
    ) -> Optional[XHSContent]:
        """
        下载小红书笔记内容 (文案 + 视频/图片)
        
        Args:
            url: 笔记链接，支持以下格式:
                 - https://www.xiaohongshu.com/explore/xxx
                 - https://www.xiaohongshu.com/discovery/item/xxx
                 - https://xhslink.com/xxx
            save_text: 是否保存文案到 txt 文件
        
        Returns:
            XHSContent 对象，包含笔记信息和下载结果
            失败返回 None
        """
        async with XHS(
            work_path=str(self.download_dir.parent),
            folder_name=self.download_dir.name,
            cookie=self.cookie,
            user_agent=self.user_agent,
            proxy=self.proxy,
            timeout=self.timeout,
            max_retry=self.max_retry,
            record_data=False,
            download_record=self.skip_existing,
            image_download=self.download_image,
            video_download=self.download_video,
            folder_mode=True,
            author_archive=True,
        ) as xhs:
            try:
                # 下载并获取数据
                result_list = await xhs.extract(
                    url,
                    download=True,
                    data=True
                )
                
                if not result_list or len(result_list) == 0:
                    # 检查 URL 是否包含 xsec_token
                    if 'xsec_token' not in url:
                        print(f"[错误] 无法获取笔记数据（URL 缺少 xsec_token）: {url}")
                        print(f"       下载他人笔记必须携带 xsec_token 参数，请使用带 token 的完整链接")
                    else:
                        print(f"[错误] 无法获取笔记数据（API 返回空，可能 Cookie 失效或被限流）: {url}")
                    return None
                
                result = result_list[0]
                if not result or not isinstance(result, dict):
                    print(f"[错误] 笔记数据格式错误（收到: {type(result).__name__}）: {url}")
                    return None
                
                # 解析内容
                content = self._parse_result(result, url)
                
                # 保存文案
                if save_text and content:
                    await self._save_text(content)
                
                print(f"[成功] 下载完成: {content.title[:30]}...")
                return content
                
            except Exception as e:
                print(f"[错误] 下载失败: {url}, 错误: {e}")
                return None
    
    async def get_info(self, url: str) -> Optional[XHSContent]:
        """
        仅获取小红书笔记信息，不下载文件
        
        Args:
            url: 笔记链接
            
        Returns:
            XHSContent 对象，失败返回 None
        """
        async with XHS(
            work_path=str(self.download_dir.parent),
            folder_name=self.download_dir.name,
            cookie=self.cookie,
            user_agent=self.user_agent,
            proxy=self.proxy,
            timeout=self.timeout,
            max_retry=self.max_retry,
            record_data=False,
            download_record=False,
            image_download=False,
            video_download=False,
        ) as xhs:
            try:
                result_list = await xhs.extract(
                    url,
                    download=False,
                    data=True
                )
                
                if not result_list or len(result_list) == 0:
                    return None
                
                result = result_list[0]
                if not result or not isinstance(result, dict):
                    return None
                
                return self._parse_result(result, url)
                
            except Exception as e:
                print(f"[错误] 获取信息失败: {url}, 错误: {e}")
                return None
    
    async def batch_download(
        self,
        urls: List[str],
        delay: float = 2.0,
        save_text: bool = True,
    ) -> List[XHSContent]:
        """
        批量下载多个笔记
        
        Args:
            urls: 笔记链接列表
            delay: 每次下载间隔时间(秒)
            save_text: 是否保存文案
            
        Returns:
            成功下载的 XHSContent 列表
        """
        results = []
        total = len(urls)
        
        for i, url in enumerate(urls, 1):
            print(f"[进度] 正在下载 {i}/{total}: {url[:50]}...")
            
            content = await self.download(url, save_text=save_text)
            if content:
                results.append(content)
            
            # 间隔延迟
            if i < total:
                await asyncio.sleep(delay)
        
        print(f"[完成] 批量下载完成，成功: {len(results)}/{total}")
        return results
    
    def _parse_result(self, result: Dict[str, Any], url: str) -> XHSContent:
        """解析 XHS 返回的结果"""
        def safe_int(value) -> int:
            try:
                return int(value) if value else 0
            except (ValueError, TypeError):
                return 0
        
        return XHSContent(
            note_id=result.get("作品ID", ""),
            title=result.get("作品标题", ""),
            description=result.get("作品描述", ""),
            tags=result.get("作品标签", ""),
            content_type=result.get("作品类型", ""),
            publish_time=result.get("发布时间", ""),
            author_name=result.get("作者昵称", ""),
            author_id=result.get("作者ID", ""),
            likes=safe_int(result.get("点赞数量", 0)),
            collects=safe_int(result.get("收藏数量", 0)),
            comments=safe_int(result.get("评论数量", 0)),
            shares=safe_int(result.get("分享数量", 0)),
            note_url=url,
            download_urls=self._parse_download_urls(result.get("下载地址", [])),
        )
    
    async def _save_text(self, content: XHSContent):
        """保存文案到文件"""
        # 构建保存路径
        author_folder = f"{content.author_id}_{self._clean_filename(content.author_name)}"
        save_dir = self.download_dir / author_folder
        save_dir.mkdir(parents=True, exist_ok=True)
        
        # 构建文件名
        title_clean = self._clean_filename(content.title) or content.note_id
        filename = f"{content.publish_time.replace(':', '.')}_{title_clean[:50]}.txt"
        filepath = save_dir / filename
        
        # 构建文案内容
        text_content = f"""标题: {content.title}

作者: {content.author_name}
发布时间: {content.publish_time}
笔记类型: {content.content_type}

标签: {content.tags}

---

{content.description}

---

笔记链接: {content.note_url}
点赞: {content.likes} | 收藏: {content.collects} | 评论: {content.comments} | 分享: {content.shares}
"""
        
        # 写入文件
        filepath.write_text(text_content, encoding="utf-8")
        content.download_path = save_dir
        print(f"[保存] 文案已保存: {filepath}")
    
    @staticmethod
    def _parse_download_urls(urls) -> List[str]:
        """解析下载地址，处理列表或字符串格式"""
        if not urls:
            return []
        if isinstance(urls, list):
            return urls
        if isinstance(urls, str):
            return urls.split()
        return []
    
    @staticmethod
    def _clean_filename(name: str) -> str:
        """清理文件名中的非法字符"""
        import re
        if not name:
            return ""
        # 替换非法字符
        name = re.sub(r'[\\/:*?"<>|]', '_', name)
        name = re.sub(r'_+', '_', name).strip('_')
        return name


# ==========================================
# 便捷函数
# ==========================================

async def download_xhs(
    url: str,
    cookie: str = None,
    download_dir: str = "downloads",
    save_text: bool = True,
) -> Optional[XHSContent]:
    """
    便捷函数: 下载单个小红书笔记
    
    Args:
        url: 笔记链接
        cookie: Cookie，如不传则从 .env 读取
        download_dir: 下载目录
        save_text: 是否保存文案
        
    Returns:
        XHSContent 对象
        
    使用示例:
    ```python
    import asyncio
    from xhs_downloader import download_xhs
    
    content = asyncio.run(download_xhs("https://www.xiaohongshu.com/explore/xxx"))
    print(f"标题: {content.title}")
    print(f"文案: {content.description}")
    ```
    """
    downloader = XHSDownloader(
        cookie=cookie,
        download_dir=download_dir,
    )
    return await downloader.download(url, save_text=save_text)


async def get_xhs_info(url: str, cookie: str = None) -> Optional[XHSContent]:
    """
    便捷函数: 仅获取笔记信息，不下载
    
    Args:
        url: 笔记链接
        cookie: Cookie，如不传则从 .env 读取
        
    Returns:
        XHSContent 对象
    """
    downloader = XHSDownloader(cookie=cookie)
    return await downloader.get_info(url)


# ==========================================
# 命令行入口
# ==========================================

async def main():
    """命令行使用示例"""

    parser = argparse.ArgumentParser(description="小红书内容下载器")
    parser.add_argument("url", nargs="?", help="笔记链接")
    parser.add_argument("-o", "--output", default="downloads", help="下载目录")
    parser.add_argument("--no-text", action="store_true", help="不保存文案")
    parser.add_argument("--info-only", action="store_true", help="仅获取信息，不下载")
    
    args = parser.parse_args()
    
    if not args.url:
        print("=" * 60)
        print("  小红书内容下载器")
        print("=" * 60)
        print("\n请输入笔记链接:")
        args.url = input("链接: ").strip()
    
    if not args.url:
        print("[错误] 链接不能为空")
        return
    
    downloader = XHSDownloader(download_dir=args.output)
    
    if args.info_only:
        content = await downloader.get_info(args.url)
        if content:
            print("\n" + "=" * 60)
            print(f"标题: {content.title}")
            print(f"作者: {content.author_name}")
            print(f"类型: {content.content_type}")
            print(f"发布时间: {content.publish_time}")
            print("-" * 60)
            print(f"文案:\n{content.description}")
            print("-" * 60)
            print(f"标签: {content.tags}")
            print(f"点赞: {content.likes} | 收藏: {content.collects} | 评论: {content.comments}")
            print("=" * 60)
    else:
        content = await downloader.download(args.url, save_text=not args.no_text)
        if content:
            print("\n[完成] 下载成功!")
            print(f"保存路径: {content.download_path or downloader.download_dir}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n程序已被用户中断")
    except Exception as e:
        print(f"\n程序运行出错: {e}")
        import traceback
        traceback.print_exc()
