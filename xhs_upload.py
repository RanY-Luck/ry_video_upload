#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小红书图文笔记批量上传工具

功能：
  - 扫描 downloads/xhs_monitor 目录（xhs_monitor.py 的下载输出）
  - 读取每篇笔记的图片 + txt 文案
  - 通过 Playwright 模拟浏览器，在 creator.xiaohongshu.com 发布图文笔记
  - 维护上传历史记录，避免重复上传
  - 支持 --dry-run 模式（只扫描，不实际上传）

使用方式：
  # 默认模式（持续监控上传）
  python xhs_upload.py

  # 单次运行后退出
  python xhs_upload.py --once

  # 试运行（只扫描打印，不上传）
  python xhs_upload.py --dry-run

  # 指定下载目录
  python xhs_upload.py --dir downloads/xhs_monitor

  # 指定间隔（秒），默认 300 秒
  python xhs_upload.py --interval 600
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import dashscope
    from dashscope import Generation
    DASHSCOPE_AVAILABLE = True
except ImportError:
    DASHSCOPE_AVAILABLE = False

try:
    import requests as _requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from dotenv import load_dotenv

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
logger = logging.getLogger("xhs_upload")

# ==========================================
# 常量
# ==========================================
CREATOR_URL = "https://creator.xiaohongshu.com/publish/publish"
LOGIN_URL = "https://creator.xiaohongshu.com"

# 图片支持的扩展名
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

# 视频支持的扩展名
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".flv", ".mkv", ".webm"}

# 上传记录文件
HISTORY_FILE = Path("logs/xhs_upload_history.txt")

# 两次上传之间休眠时间（秒），避免风控
UPLOAD_SLEEP = 30

# AI 润色模型
AI_MODEL = "qwen-turbo"

# Bark 服务器
BARK_SERVER = "https://api.day.app"


# ==========================================
# AI 润色
# ==========================================
class XHSAIPolisher:
    """
    使用阿里百炼 qwen-turbo 对小红书笔记标题和正文进行润色二创。
    失败时安全降级，返回原始文案，不阻断上传流程。
    """

    def __init__(self):
        self.api_key = os.getenv("DASHSCOPE_API_KEY", "")
        self.available = DASHSCOPE_AVAILABLE and bool(self.api_key)
        if self.available:
            dashscope.api_key = self.api_key

    def polish(self, title: str, description: str) -> Dict[str, str]:
        """
        润色标题和描述。

        Args:
            title:       原始标题
            description: 原始正文

        Returns:
            {"title": 润色后标题, "description": 润色后正文}
            失败时返回原始值。
        """
        if not self.available:
            if not DASHSCOPE_AVAILABLE:
                logger.warning("[AI润色] dashscope 未安装，跳过润色（pip install dashscope）")
            else:
                logger.warning("[AI润色] 未配置 DASHSCOPE_API_KEY，跳过润色")
            return {"title": title, "description": description}

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"[AI润色] 正在润色: {title[:30]}（第 {attempt}/{max_retries} 次）")

                prompt = f"""请对以下小红书笔记进行润色二创，保留原意，风格更活泼自然，适合小红书平台。
要求：
- 标题：控制在 20 字以内，加入情感钩子，可用 1-2 个 emoji
- 正文：保留原有核心信息，语气更亲切，适当加 emoji，结尾可追加 3~5 个话题标签（#话题 格式）
- 严格按以下 JSON 格式输出，不要输出任何其他内容：
{{
  "title": "润色后的标题",
  "description": "润色后的正文"
}}

原始标题：{title}
原始正文：{description if description else '（无正文）'}"""

                response = Generation.call(
                    model=AI_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": "你是一位拥有 5 年经验的小红书爆款文案专家，擅长把普通文案改写成高互动率笔记。",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    result_format="message",
                )

                if response.status_code != 200:
                    raise ValueError(f"API 返回异常状态码: {response.status_code}, 信息: {response.message}")

                raw = response.output.choices[0].message.content.strip()

                # 提取 JSON（兼容 AI 在回答前/后多余文字的情况）
                json_match = re.search(r'\{[\s\S]*\}', raw)
                if not json_match:
                    raise ValueError(f"未找到 JSON 内容，原始输出: {raw[:200]}")

                result = json.loads(json_match.group())
                polished_title = result.get("title", "").strip() or title
                polished_desc = result.get("description", "").strip() or description

                logger.info(f"[AI润色] ✅ 润色完成")
                logger.info(f"[AI润色] 标题: {title[:20]} → {polished_title[:30]}")
                return {"title": polished_title, "description": polished_desc}

            except Exception as e:
                logger.warning(f"[AI润色] ⚠️ 第 {attempt} 次失败: {e}")
                if attempt < max_retries:
                    time.sleep(2)

        logger.error("[AI润色] ❌ 润色最终失败，使用原始文案继续上传")
        return {"title": title, "description": description}


# ==========================================
# Bark 推送
# ==========================================
def bark_notify_success(note_title: str):
    """
    上传成功后推送 Bark 通知。
    安全调用，失败时仅打印警告，不影响主流程。

    Args:
        note_title: 已发布的笔记标题
    """
    if not REQUESTS_AVAILABLE:
        logger.warning("[Bark] requests 未安装，跳过推送")
        return

    bark_key = os.getenv("BARK_KEY", "").strip()
    if not bark_key:
        logger.warning("[Bark] 未配置 BARK_KEY，跳过推送")
        return

    try:
        title_encoded = "📤 小红书笔记已发布"
        body = note_title[:50]  # Bark URL 参数，控制长度
        url = f"{BARK_SERVER}/{bark_key}/{title_encoded}/{body}"
        params = {
            "group": "小红书上传",
            "sound": "fanfare",
            "icon": "https://api.iconify.design/mdi:note-check-outline.svg",
        }
        resp = _requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") == 200:
            logger.info(f"[Bark] ✅ 推送成功: {note_title[:20]}")
        else:
            logger.warning(f"[Bark] 推送返回: {result}")
    except Exception as e:
        logger.warning(f"[Bark] 推送失败（不影响上传）: {e}")


# ==========================================
# 历史记录管理
# ==========================================
class UploadHistory:
    """管理已上传笔记的记录，避免重复上传"""

    def __init__(self, history_file: Path = HISTORY_FILE):
        self.history_file = history_file
        self._uploaded: set = self._load()

    def _load(self) -> set:
        if not self.history_file.exists():
            return set()
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                return {line.strip() for line in f if line.strip()}
        except Exception as e:
            logger.warning(f"[历史] 读取记录失败: {e}")
            return set()

    def has(self, note_id: str) -> bool:
        return note_id in self._uploaded

    def add(self, note_id: str):
        self._uploaded.add(note_id)
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.history_file, "a", encoding="utf-8") as f:
                f.write(f"{note_id}\n")
        except Exception as e:
            logger.error(f"[历史] 保存记录失败: {e}")

    def count(self) -> int:
        return len(self._uploaded)


# ==========================================
# 笔记内容解析
# ==========================================
def parse_note_folder(folder: Path) -> Optional[Dict]:
    """
    解析下载的笔记文件夹，提取标题、描述、图片/视频路径。
    自动判断笔记类型：含 mp4 则为视频笔记，否则为图文笔记。

    目录结构（由 xhs_monitor.py 生成）：
      {note_id}_{标题}/
        {标题}.txt
        {标题}_0.jpg       ← 图文笔记
        or
        {标题}_0.mp4       ← 视频笔记

    返回字段：
      note_type: "video" | "image"
      videos:    视频文件路径列表（视频笔记时有效）
      images:    图片文件路径列表（图文笔记时有效）
    """
    # 从文件夹名提取 note_id（格式：{note_id}_{标题}）
    folder_name = folder.name
    parts = folder_name.split("_", 1)
    note_id = parts[0] if len(parts[0]) >= 16 else folder_name  # XHS note_id 通常 24 字符
    # 更精确地从真实 ID 格式提取
    id_match = re.match(r"^([a-f0-9]{24})", folder_name, re.IGNORECASE)
    if id_match:
        note_id = id_match.group(1)
    else:
        note_id = folder_name  # 兜底使用文件夹名作为唯一 ID

    # 查找 txt 文案文件
    txt_files = list(folder.glob("*.txt"))
    if not txt_files:
        logger.debug(f"[扫描] {folder.name}: 无 txt 文案文件，跳过")
        return None

    txt_file = txt_files[0]

    # 解析 txt 文件
    title = ""
    author = ""
    description = ""
    try:
        content = txt_file.read_text(encoding="utf-8")
        lines = content.splitlines()
        meta_done = False
        desc_lines = []

        for line in lines:
            if not meta_done:
                if line.startswith("标题:") or line.startswith("标题："):
                    title = line.split(":", 1)[-1].strip() if ":" in line else line.split("：", 1)[-1].strip()
                elif line.startswith("作者:") or line.startswith("作者："):
                    author = line.split(":", 1)[-1].strip() if ":" in line else line.split("：", 1)[-1].strip()
                elif line.startswith("ID:"):
                    # 从 txt 里读取真实 note_id
                    real_id = line.split(":", 1)[-1].strip()
                    if real_id:
                        note_id = real_id
                elif line == "" and title:
                    # 遇到第一个空行（且已解析到标题）后，后续内容为正文
                    meta_done = True
            else:
                desc_lines.append(line)

        description = "\n".join(desc_lines).strip()
    except Exception as e:
        logger.warning(f"[解析] 读取 {txt_file} 失败: {e}")
        title = folder_name
        description = ""

    if not title:
        title = folder_name

    # 收集视频文件（按文件名排序）
    video_files = sorted(
        [f for f in folder.iterdir() if f.suffix.lower() in VIDEO_EXTS],
        key=lambda x: x.name,
    )

    # 收集图片文件（按文件名排序）
    image_files = sorted(
        [f for f in folder.iterdir() if f.suffix.lower() in IMAGE_EXTS],
        key=lambda x: x.name,
    )

    # 判断笔记类型：有视频优先作为视频笔记
    if video_files:
        note_type = "video"
        logger.debug(f"[扫描] {folder.name}: 视频笔记（{len(video_files)} 个视频文件）")
    elif image_files:
        note_type = "image"
        logger.debug(f"[扫描] {folder.name}: 图文笔记（{len(image_files)} 张图片）")
    else:
        logger.debug(f"[扫描] {folder.name}: 无图片/视频文件，跳过")
        return None

    return {
        "note_id": note_id,
        "note_type": note_type,    # "video" 或 "image"
        "folder": folder,
        "title": title,
        "author": author,
        "description": description,
        "images": image_files,     # 图文笔记时使用
        "videos": video_files,     # 视频笔记时使用
    }


# ==========================================
# 目录扫描器
# ==========================================
class NoteScanner:
    """扫描 xhs_monitor 下载目录，收集待上传的笔记"""

    def __init__(self, download_dir: str, history: UploadHistory):
        self.download_dir = Path(download_dir)
        self.history = history

    def scan(self) -> List[Dict]:
        """
        扫描并返回所有待上传的笔记列表。

        目录结构：
          download_dir/
            {作者名}/
              {note_id}_{标题}/   ← 这一层才是笔记文件夹
        """
        if not self.download_dir.exists():
            logger.warning(f"[扫描] 下载目录不存在: {self.download_dir}")
            return []

        pending = []

        # 遍历 {作者名} 子目录
        for author_dir in sorted(self.download_dir.iterdir()):
            if not author_dir.is_dir():
                continue
            # 跳过隐藏目录（如 .seen）
            if author_dir.name.startswith("."):
                continue

            # 遍历 {note_id}_{标题} 子目录
            for note_folder in sorted(author_dir.iterdir()):
                if not note_folder.is_dir():
                    continue

                note = parse_note_folder(note_folder)
                if note is None:
                    continue

                if self.history.has(note["note_id"]):
                    logger.debug(f"[扫描] 跳过已上传: {note['note_id']} — {note['title'][:20]}")
                    continue

                pending.append(note)

        logger.info(f"[扫描] 发现 {len(pending)} 篇待上传笔记")
        return pending


# ==========================================
# 小红书上传器（Playwright）
# ==========================================
class XHSUploader:
    """
    使用 Playwright 模拟浏览器，在 creator.xiaohongshu.com 发布图文笔记。
    """

    def __init__(self, cookie: str = "", account_file: str = ""):
        self.cookie = cookie or os.getenv("XHS_COOKIE", "")
        self.account_file = Path(account_file) if account_file else None
        # 从 .env 读取账号文件路径
        if not self.account_file:
            env_account = os.getenv("XHS_UPLOAD_ACCOUNT", "")
            if env_account:
                self.account_file = Path(env_account)

    def _parse_cookie_str(self, cookie_str: str) -> List[Dict]:
        """将 cookie 字符串解析为 Playwright cookie 格式"""
        cookies = []
        for item in cookie_str.split(";"):
            item = item.strip()
            if "=" not in item:
                continue
            name, value = item.split("=", 1)
            cookies.append({
                "name": name.strip(),
                "value": value.strip(),
                "domain": ".xiaohongshu.com",
                "path": "/",
            })
        return cookies

    async def _inject_cookies(self, context):
        """向浏览器上下文注入 Cookie"""
        injected = 0

        # 优先读取账号 JSON 文件（Playwright 格式）
        if self.account_file and self.account_file.exists():
            try:
                with open(self.account_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                cookies = saved if isinstance(saved, list) else saved.get("cookies", [])
                if cookies:
                    await context.add_cookies(cookies)
                    injected = len(cookies)
                    logger.info(f"[登录] 从账号文件注入 {injected} 个 Cookie: {self.account_file}")
                    return injected
            except Exception as e:
                logger.warning(f"[登录] 读取账号文件失败: {e}，尝试使用 XHS_COOKIE 字符串")

        # 使用 XHS_COOKIE 字符串
        if self.cookie:
            cookies = self._parse_cookie_str(self.cookie)
            if cookies:
                await context.add_cookies(cookies)
                injected = len(cookies)
                logger.info(f"[登录] 从 XHS_COOKIE 注入 {injected} 个 Cookie")

        return injected

    async def _wait_for_login(self, page) -> bool:
        """
        检查是否已登录。
        如果未登录，等待用户在浏览器中手动扫码，最多等待 120 秒。
        """
        # 访问创作者主页
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        # 判断是否需要登录（URL 跳转到登录页或出现二维码）
        current_url = page.url
        if "creator.xiaohongshu.com" in current_url and "login" not in current_url:
            logger.info("[登录] ✓ Cookie 有效，已登录")
            return True

        # 等待手动扫码
        logger.warning("[登录] Cookie 无效或未登录，请在浏览器中扫码登录...")
        logger.warning("[登录] 等待最多 120 秒...")

        for i in range(120):
            await asyncio.sleep(1)
            url = page.url
            if "creator.xiaohongshu.com" in url and "login" not in url:
                logger.info("[登录] ✓ 扫码登录成功！")
                return True

        logger.error("[登录] ✗ 登录超时")
        return False

    async def _save_account(self, context):
        """登录成功后保存 Cookie 到账号文件"""
        if not self.account_file:
            return
        try:
            self.account_file.parent.mkdir(parents=True, exist_ok=True)
            cookies = await context.cookies()
            with open(self.account_file, "w", encoding="utf-8") as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
            logger.info(f"[登录] Cookie 已保存到: {self.account_file}")
        except Exception as e:
            logger.warning(f"[登录] 保存 Cookie 失败: {e}")

    async def upload_note(
        self,
        page,
        title: str,
        description: str,
        image_paths: List[Path],
        note_type: str = "image",
        video_paths: Optional[List[Path]] = None,
    ) -> bool:
        """
        在 creator.xiaohongshu.com 发布一篇笔记。

        note_type = "image" → 上传图文（image_paths 为图片列表）
        note_type = "video" → 上传视频（video_paths[0] 为视频文件）

        DOM 结构（通过实际页面检查确认 2026-02-27）：
          - 视频 tab:    div.creator-tab（含文字"上传视频"）
          - 图文 tab:    div.creator-tab（含文字"上传图文"）
          - 图片 input:  input.upload-input（图文模式 accept=".jpg,.jpeg,.png,.webp", multiple=true）
          - 视频 input:  input.upload-input（视频模式 accept=".mp4,.mov,.flv..." multiple=false）
          - 标题/正文:   上传媒体后动态渲染
          - 发布按钮:    button 含文字"发布"

        Returns:
            True 表示发布成功
        """
        video_paths = video_paths or []
        type_label = "视频" if note_type == "video" else "图文"
        logger.info(f"[上传] 开始发布 [{type_label}]: {title[:30]}")
        if note_type == "video":
            logger.info(f"[上传] 视频文件: {len(video_paths)} 个")
        else:
            logger.info(f"[上传] 图片数量: {len(image_paths)}")


        try:
            # ── 步骤 1：打开发布页，等待页面完整渲染 ──────────────────
            await page.goto(CREATOR_URL, wait_until="domcontentloaded", timeout=30000)
            # 等待 creator-tab 出现（确认页面 JS 已渲染）
            try:
                await page.wait_for_selector(".creator-tab", timeout=10000)
                logger.info("[上传] ✓ 页面已渲染（检测到 .creator-tab）")
            except Exception:
                logger.warning("[上传] .creator-tab 超时，继续等待 3 秒")
                await page.wait_for_timeout(3000)

            # ── 步骤 2：切换到对应 tab（用 JS 找可见元素后 evaluate click，避免视口外超时）
            # 实测：4个 .creator-tab 中有1个隐藏（BoundingRect 在负坐标区），需过滤
            tab_keyword = "图文" if note_type == "image" else "视频"
            switched = False

            # 用 JS 找到可见且含关键字的 tab，直接在页面内点击（绕过 Playwright 的视口检测）
            clicked = await page.evaluate(f"""
                () => {{
                    const tabs = Array.from(document.querySelectorAll('.creator-tab'));
                    for (const tab of tabs) {{
                        const rect = tab.getBoundingClientRect();
                        const visible = rect.width > 0 && rect.height > 0 && rect.x >= 0 && rect.y >= 0;
                        if (visible && tab.textContent.includes('{tab_keyword}')) {{
                            tab.click();
                            return tab.textContent.trim();
                        }}
                    }}
                    return null;
                }}
            """)
            if clicked:
                await page.wait_for_timeout(1500)
                logger.info(f"[上传] ✓ 已通过 JS 点击 tab: '{clicked}'")
                switched = True
            else:
                logger.warning(f"[上传] JS 方式未找到可见的'{tab_keyword}' tab，截图后继续")
                await _save_debug_screenshot(page, f"{title}_no_tab")

            # ── 步骤 3：等待 input 就绪，上传媒体文件 ─────────────────
            upload_input = None

            if note_type == "video":
                # 视频模式：input.upload-input，accept 含 mp4
                try:
                    await page.wait_for_selector('input.upload-input[accept*="mp4"]', timeout=8000)
                    upload_input = await page.query_selector('input.upload-input[accept*="mp4"]')
                    logger.info("[上传] ✓ 找到视频 file input")
                except Exception:
                    upload_input = await page.query_selector("input.upload-input")
                    if upload_input:
                        logger.info("[上传] ✓ 找到 upload-input（降级）")

                if not upload_input:
                    logger.error("[上传] ✗ 未找到视频上传 input")
                    await _save_debug_screenshot(page, f"{title}_no_input")
                    return False

                vfile = next((p for p in video_paths if p.exists()), None)
                if not vfile:
                    logger.error("[上传] ✗ 视频文件不存在")
                    return False
                logger.info(f"[上传] 正在上传视频: {vfile.name}")
                await upload_input.set_input_files(str(vfile.absolute()))

            else:
                # 图文模式：input.upload-input，accept 含 jpg，multiple=true
                try:
                    await page.wait_for_selector('input.upload-input[accept*="jpg"]', timeout=8000)
                    upload_input = await page.query_selector('input.upload-input[accept*="jpg"]')
                    logger.info("[上传] ✓ 找到图文 file input")
                except Exception:
                    upload_input = await page.query_selector("input.upload-input")
                    if upload_input:
                        logger.info("[上传] ✓ 找到 upload-input（降级）")

                if not upload_input:
                    logger.error("[上传] ✗ 未找到图片上传 input")
                    await _save_debug_screenshot(page, f"{title}_no_input")
                    return False

                file_list = [str(p.absolute()) for p in image_paths if p.exists()]
                missing = [str(p) for p in image_paths if not p.exists()]
                if missing:
                    logger.warning(f"[上传] 以下图片不存在，跳过: {missing}")
                if not file_list:
                    logger.error("[上传] ✗ 所有图片文件均不存在")
                    return False
                logger.info(f"[上传] 正在上传 {len(file_list)} 张图片: {[Path(f).name for f in file_list]}")
                await upload_input.set_input_files(file_list)

            # ── 步骤 4：等待编辑区渲染（上传后动态注入） ──────────────
            # 实测：标题框为 input.d-text，正文为 div.tiptap.ProseMirror
            logger.info("[上传] 等待编辑区渲染...")
            try:
                await page.wait_for_selector(
                    'input.d-text, input[placeholder*="填写标题"], div.ProseMirror',
                    timeout=60000,
                )
                logger.info("[上传] ✓ 编辑区已渲染")
            except Exception:
                logger.warning("[上传] 编辑区等待超时，继续尝试")
                await page.wait_for_timeout(5000)

            await page.wait_for_timeout(2000)
            await _save_debug_screenshot(page, f"{title}_after_upload")

            # ── 步骤 5：填写标题 ──────────────────────────────────────
            # 实测：input.d-text，placeholder="填写标题会有更多赞哦"
            title_short = title[:20]
            title_input = (
                await page.query_selector('input.d-text')
                or await page.query_selector('input[placeholder*="填写标题"]')
                or await page.query_selector('input[placeholder*="标题"]')
            )
            if title_input:
                await title_input.click()
                await title_input.click(click_count=3)
                await title_input.fill(title_short)
                logger.info(f"[上传] ✓ 已填写标题: {title_short}")
            else:
                logger.warning("[上传] 未找到标题输入框，跳过")

            await page.wait_for_timeout(500)

            # ── 步骤 6：填写正文描述 ──────────────────────────────────
            # 实测：div.tiptap.ProseMirror[contenteditable="true"]（ProseMirror 富文本）
            # ProseMirror 不支持 fill()，必须 click() 后用 keyboard.type()
            desc_input = (
                await page.query_selector('div.tiptap.ProseMirror[contenteditable="true"]')
                or await page.query_selector('div.ProseMirror[contenteditable="true"]')
                or await page.query_selector('div.tiptap[contenteditable="true"]')
            )
            # 降级：找所有可见 contenteditable，取第一个非标题的
            if not desc_input:
                all_editable = await page.query_selector_all('div[contenteditable="true"]')
                visible_editable = []
                for el in all_editable:
                    if await el.is_visible():
                        visible_editable.append(el)
                if visible_editable:
                    desc_input = visible_editable[0]
                    logger.info(f"[上传] 降级：找到 {len(visible_editable)} 个可见 contenteditable，取第1个")

            if desc_input:
                await desc_input.click()
                await page.wait_for_timeout(300)
                full_desc = description if description else title
                # ProseMirror 需要用 keyboard.type 而非 fill
                await page.keyboard.type(full_desc, delay=30)
                logger.info(f"[上传] ✓ 已填写正文 ({len(full_desc)} 字)")
            else:
                logger.warning("[上传] 未找到正文输入框，跳过")

            await page.wait_for_timeout(1000)

            # ── 步骤 7：等待上传完成，点击发布按钮 ───────────────────
            # 图片/视频上传到服务器需要时间，发布按钮可能处于 disabled 状态
            # 策略：最多等 120 秒（10次×12秒），直到按钮从 disabled 变为可用
            logger.info("[上传] 等待媒体上传至服务器完成...")

            publish_btn = None
            MAX_WAIT_ROUNDS = 10   # 最多重试轮数
            WAIT_PER_ROUND = 12    # 每轮等待秒数

            for attempt in range(MAX_WAIT_ROUNDS):
                # 检查是否还在上传中（有进度条/loading元素）
                uploading = await page.query_selector(
                    '[class*="uploading"], [class*="progress"]:not([value="100"]), '
                    '[class*="loading"]:not([class*="button"]):not([class*="btn"])'
                )
                if uploading:
                    logger.info(f"[上传] 第 {attempt+1} 轮：检测到上传进度元素，等待 {WAIT_PER_ROUND} 秒...")
                    await page.wait_for_timeout(WAIT_PER_ROUND * 1000)
                    continue

                # 找发布按钮：文字精确匹配"发布"，可见，未禁用
                btns = await page.query_selector_all("button")
                for btn in btns:
                    if not await btn.is_visible():
                        continue
                    btn_text = (await btn.inner_text()).strip()
                    is_disabled = await btn.get_attribute("disabled")
                    if btn_text == "发布":
                        if is_disabled is None:
                            publish_btn = btn
                            logger.info(f"[上传] ✓ 找到可用发布按钮（第 {attempt+1} 轮）")
                        else:
                            logger.info(f"[上传] 第 {attempt+1} 轮：发布按钮 disabled，等待 {WAIT_PER_ROUND} 秒...")
                        break

                if publish_btn:
                    break

                await page.wait_for_timeout(WAIT_PER_ROUND * 1000)

            if not publish_btn:
                logger.error(f"[上传] ✗ 等待 {MAX_WAIT_ROUNDS * WAIT_PER_ROUND} 秒后仍未找到可用发布按钮")
                await _save_debug_screenshot(page, f"{title}_no_publish_btn")
                return False

            await publish_btn.scroll_into_view_if_needed()
            await publish_btn.click()
            logger.info("[上传] ✓ 已点击发布按钮")

            # ── 步骤 8：等待发布成功 ──────────────────────────────────
            await page.wait_for_timeout(3000)
            current_url = page.url

            if "manage" in current_url or "success" in current_url:
                logger.info(f"[上传] ✓ 发布成功（URL 跳转）: {title[:30]}")
                return True

            # 查找 toast / 提示元素
            success_el = await page.query_selector('[class*="success"], [class*="toast"]')
            if success_el:
                success_text = (await success_el.inner_text()).strip()
                logger.info(f"[上传] ✓ 成功提示: '{success_text}'")
                return True

            # 再等 5 秒
            await page.wait_for_timeout(5000)
            if page.url != CREATOR_URL:
                logger.info(f"[上传] ✓ 疑似成功（URL 已变化）: {title[:30]}")
                return True

            logger.warning(f"[上传] ? 未检测到明确成功标志，保守记为成功: {title[:30]}")
            await _save_debug_screenshot(page, f"{title}_final")
            return True

        except Exception as e:
            logger.error(f"[上传] ✗ 发布异常: {e}")
            import traceback
            traceback.print_exc()
            await _save_debug_screenshot(page, f"{title}_error")
            return False

    async def run_upload_session(
        self,
        notes: List[Dict],
        dry_run: bool = False,
        history: Optional[UploadHistory] = None,
    ) -> Tuple[int, int]:
        """
        启动浏览器会话，批量上传笔记。

        Returns:
            (success_count, fail_count)
        """
        if dry_run:
            logger.info("[试运行] dry-run 模式，不执行实际上传")
            for i, note in enumerate(notes, 1):
                logger.info(
                    f"  [{i}] ID={note['note_id']} | 标题={note['title'][:30]} | "
                    f"图片={len(note['images'])} | 描述={len(note['description'])} 字"
                )
            return 0, 0

        if not notes:
            logger.info("[上传] 没有待上传的笔记")
            return 0, 0

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("[Playwright] 未安装，请运行: pip install playwright && playwright install chromium")
            return 0, len(notes)

        success = 0
        fail = 0

        # 初始化 AI 润色器（在浏览器启动前完成，避免异步干扰）
        ai_polisher = XHSAIPolisher()

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

        try:
            # 注入 Cookie
            injected = await self._inject_cookies(context)
            if injected == 0:
                logger.warning("[登录] 未配置 Cookie，将需要扫码登录")

            page = await context.new_page()

            # 检查登录状态（必要时等待扫码）
            logged_in = await self._wait_for_login(page)
            if not logged_in:
                logger.error("[登录] 登录失败，中止上传")
                return 0, len(notes)

            # 保存登录后的 Cookie
            await self._save_account(context)

            # 逐一上传笔记
            for idx, note in enumerate(notes, 1):
                note_id = note["note_id"]
                note_type = note.get("note_type", "image")
                title = note["title"]
                description = note["description"]
                images = note.get("images", [])
                videos = note.get("videos", [])

                type_label = "视频" if note_type == "video" else "图文"
                logger.info(f"\n{'─' * 50}")
                logger.info(f"[进度] {idx}/{len(notes)} — [{type_label}] {title[:40]}")
                if note_type == "video":
                    logger.info(f"[进度] ID: {note_id} | 视频: {len(videos)} 个")
                else:
                    logger.info(f"[进度] ID: {note_id} | 图片: {len(images)} 张")

                # ── AI 润色文案（上传前） ─────────────────────────────
                polished = ai_polisher.polish(title, description)
                upload_title = polished["title"]
                upload_desc = polished["description"]

                ok = await self.upload_note(
                    page, upload_title, upload_desc,
                    image_paths=images,
                    note_type=note_type,
                    video_paths=videos,
                )

                if ok:
                    success += 1
                    if history:
                        history.add(note_id)
                    logger.info(f"[进度] ✓ 第 {idx} 篇上传成功")
                    # ── Bark 推送通知 ────────────────────────────────
                    bark_notify_success(upload_title)
                else:
                    fail += 1
                    logger.warning(f"[进度] ✗ 第 {idx} 篇上传失败")

                # 避免风控：两次上传之间休眠
                if idx < len(notes):
                    logger.info(f"[节奏] 等待 {UPLOAD_SLEEP} 秒后继续...")
                    await asyncio.sleep(UPLOAD_SLEEP)

        except Exception as e:
            logger.error(f"[会话] 整体异常: {e}")
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

        return success, fail


# ==========================================
# 调试工具
# ==========================================
async def _save_debug_screenshot(page, label: str):
    """保存调试截图"""
    try:
        Path("logs").mkdir(exist_ok=True)
        safe_label = re.sub(r'[\\/:*?"<>|]', '_', label)[:30]
        path = f"logs/xhs_upload_debug_{safe_label}.png"
        await page.screenshot(path=path, full_page=True)
        logger.info(f"[调试] 已保存截图: {path}")
    except Exception:
        pass


# ==========================================
# 主调度器
# ==========================================
class XHSUploadScheduler:
    """上传调度器，支持单次和持续循环模式"""

    def __init__(
        self,
        download_dir: str = "downloads/xhs_monitor",
        interval: int = 300,
        cookie: str = "",
        account_file: str = "",
        run_once: bool = False,
        dry_run: bool = False,
    ):
        load_dotenv()

        self.download_dir = download_dir or os.getenv("XHS_UPLOAD_DIR", "downloads/xhs_monitor")
        self.interval = interval
        self.run_once = run_once
        self.dry_run = dry_run

        self.history = UploadHistory()
        self.scanner = NoteScanner(self.download_dir, self.history)
        self.uploader = XHSUploader(
            cookie=cookie,
            account_file=account_file,
        )

        logger.info(f"[初始化] 下载目录: {self.download_dir}")
        logger.info(f"[初始化] 已上传记录: {self.history.count()} 条")
        logger.info(f"[初始化] 模式: {'试运行' if dry_run else '单次' if run_once else '持续循环'}")

    async def run_once_round(self) -> Tuple[int, int]:
        """执行一轮扫描 + 上传"""
        notes = self.scanner.scan()
        if not notes:
            return 0, 0

        success, fail = await self.uploader.run_upload_session(
            notes,
            dry_run=self.dry_run,
            history=self.history,
        )
        return success, fail

    async def run(self):
        """启动主循环"""
        self._print_banner()

        if self.run_once or self.dry_run:
            logger.info("[调度] 单次模式，执行一轮后退出")
            success, fail = await self.run_once_round()
            logger.info(f"[调度] 完成: 成功 {success} 篇，失败 {fail} 篇")
            return

        # 持续循环
        round_num = 0
        while True:
            round_num += 1
            logger.info(f"\n{'=' * 60}")
            logger.info(f"  第 {round_num} 轮上传  |  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"{'=' * 60}")

            success, fail = await self.run_once_round()
            logger.info(f"[调度] 本轮完成: 成功 {success} 篇，失败 {fail} 篇")
            logger.info(f"[调度] {self.interval} 秒后进行下一轮检查...")
            logger.info(
                f"[调度] 下次时间: {datetime.fromtimestamp(time.time() + self.interval).strftime('%H:%M:%S')}"
            )

            try:
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                logger.info("[调度] 上传已停止")
                break

    def _print_banner(self):
        print()
        print("=" * 60)
        print("  📤 小红书图文笔记批量上传工具")
        print("=" * 60)
        print(f"  下载目录: {self.download_dir}")
        print(f"  已上传记录: {self.history.count()} 条")
        print(f"  Cookie: {'✓ 已配置' if self.uploader.cookie else '✗ 未配置（需扫码）'}")
        print(f"  账号文件: {self.uploader.account_file or '未配置'}")
        print(f"  模式: {'【试运行】只扫描不上传' if self.dry_run else '单次' if self.run_once else '持续循环'}")
        if not self.dry_run and not self.run_once:
            print(f"  检查间隔: {self.interval} 秒")
        print("=" * 60)
        print()


# ==========================================
# 命令行入口
# ==========================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="小红书图文笔记批量上传工具 — 上传 xhs_monitor 下载的内容",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 扫描默认目录并上传（单次）
  python xhs_upload.py --once

  # 试运行，只打印待上传内容
  python xhs_upload.py --dry-run

  # 持续循环，每 5 分钟检查一次
  python xhs_upload.py --interval 300

  # 指定下载目录
  python xhs_upload.py --dir downloads/xhs_monitor --once

  # 指定 Cookie
  python xhs_upload.py --cookie "a1=xxx;web_session=yyy" --once
        """,
    )

    parser.add_argument(
        "--dir",
        type=str,
        default="",
        help="下载目录（默认读取 .env 的 XHS_UPLOAD_DIR 或 XHS_MONITOR_DIR）",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=0,
        help="轮询间隔（秒），持续循环模式有效，默认 300 秒",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="只运行一轮后退出",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="试运行：只扫描和打印待上传内容，不实际上传",
    )
    parser.add_argument(
        "--cookie",
        type=str,
        default="",
        help="小红书 Cookie 字符串（覆盖 .env 配置）",
    )
    parser.add_argument(
        "--account",
        type=str,
        default="",
        help="账号 Cookie JSON 文件路径（覆盖 .env 配置）",
    )
    return parser.parse_args()


async def main():
    load_dotenv()
    args = parse_args()

    # 下载目录：命令行 > .env XHS_UPLOAD_DIR > .env XHS_MONITOR_DIR > 默认值
    download_dir = (
        args.dir
        or os.getenv("XHS_UPLOAD_DIR", "")
        or os.getenv("XHS_MONITOR_DIR", "downloads/xhs_monitor")
    )

    # 间隔：命令行 > .env > 默认 300 秒
    interval = args.interval or int(os.getenv("XHS_UPLOAD_INTERVAL", "300"))

    scheduler = XHSUploadScheduler(
        download_dir=download_dir,
        interval=interval,
        cookie=args.cookie,
        account_file=args.account,
        run_once=args.once,
        dry_run=args.dry_run,
    )

    try:
        await scheduler.run()
    except KeyboardInterrupt:
        print("\n\n[中断] 程序已被用户停止 (Ctrl+C)")


if __name__ == "__main__":
    asyncio.run(main())
