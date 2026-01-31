"""
独立视频号上传工具
功能: 上传 Upload/videos 目录下已去重的视频到视频号
"""
import time
import json
import shutil
import asyncio
import os
import re
import cv2
import sys
import dashscope
import traceback
from pathlib import Path
from dashscope import MultiModalConversation
from typing import Dict
from Upload.utils.log import logger as logging
from Upload.utils.utils_common import setup_project_paths, setup_logging
from Upload.uploader.tencent_uploader.main import TencentVideo
from Upload.utils.bark_notifier import BarkNotifier
from Upload.utils.config_loader import config
from Upload.uploader.tencent_uploader.main import weixin_setup
from contextlib import contextmanager
from Upload.uploader.tencent_uploader.main import cookie_auth

# 设置项目路径
setup_project_paths()

# 配置日志
logger = setup_logging('logs/standalone_upload.log')


@contextmanager
def suppress_stderr():
    """Suppress stderr/stdout from C libraries"""
    try:
        # Save stderr
        original_stderr_fd = 2  # Standard stderr fd
        saved_stderr_fd = os.dup(original_stderr_fd)

        # Open devnull
        devnull = os.open(os.devnull, os.O_WRONLY)

        # Replace stderr with devnull
        os.dup2(devnull, original_stderr_fd)

        try:
            yield
        finally:
            # Restore stderr
            os.dup2(saved_stderr_fd, original_stderr_fd)
            os.close(saved_stderr_fd)
            os.close(devnull)
    except Exception:
        # If any OS error, just run the code
        yield


class StandaloneUploadConfig:
    """独立上传工具配置类"""

    def __init__(self):
        # 从配置文件加载路径
        self.UPLOAD_DIR = config.get_path('upload_dir')
        self.VIDEO_DIR = config.get_path('video_output_dir')
        self.ACCOUNT_FILE = config.get_path('account_file')

        # 从配置文件加载 AI 配置
        self.DASHSCOPE_API_KEY = config.dashscope_api_key

        # 从配置文件加载上传配置
        self.CATEGORY = config.upload_category
        self.PUBLISH_DATE = config.publish_date
        self.DELETE_AFTER_UPLOAD = config.delete_after_upload

        # nas目录配置
        self.NAS_DIR = config.nas_dir
        self.DOCKER_MODE = config.docker_mode

        # 验证路径
        self._validate_paths()

    def _validate_paths(self):
        """验证必要的路径是否存在"""
        # 自动创建视频目录
        self.VIDEO_DIR.mkdir(parents=True, exist_ok=True)

        # 检查账号配置文件
        if not self.ACCOUNT_FILE.exists():
            logging.warning(f"账号配置文件不存在: {self.ACCOUNT_FILE}")
            logging.warning("请先运行 Upload/vx_cookie.py 获取账号 cookie")

        logging.info(f"视频目录: {self.VIDEO_DIR}")
        logging.info(f"账号配置: {self.ACCOUNT_FILE}")
        if self.NAS_DIR:
            logging.info(f"NAS 目录: {self.NAS_DIR}")
        if self.DOCKER_MODE:
            logging.info("已启用 Docker 模拟模式")


class AIAnalyzer:
    """AI 分析类: 使用阿里百炼 AI 分析视频生成标题和标签"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        dashscope.api_key = api_key

    def analyze_video(self, video_path: Path, original_title: str = "") -> Dict[str, str]:
        """使用 AI 分析视频,生成标题和标签 (带重试机制)
        
        Args:
            video_path: 视频文件路径
            original_title: 原始标题 (可选)
        
        Returns:
            包含 title 和 tag 的字典
        """
        max_retries = 5
        retry_delay = 2

        for attempt in range(1, max_retries + 1):
            try:
                logging.info(f"AI 分析视频: {video_path.name} (第 {attempt}/{max_retries} 次尝试)")

                messages = [
                    {
                        "role": "system",
                        "content": [{
                            "type": "text",
                            "text": """
                            你是一位拥有10年经验的资深短视频运营专家,擅长跨平台内容重构与爆款公式设计。
                            你会分析视频内容,结合中国用户心理,利用悬念前置、感官刺激、认知冲突等钩子设计爆款中文标题和热门中文标签。
                            标题中可以适当使用1-2个表情图标,标签数量大于8个。
                            严格按照以下 JSON 格式输出结果:
                            {
                                "title": "标题",
                                "tag": "标签1,标签2,标签3,标签4,标签5,标签6,标签7,标签8"
                            }
                            """
                        }]
                    },
                    {
                        "role": "user",
                        "content": [
                            {"video": f"file://{video_path}"},
                            {"text": f"原始标题: {original_title}" if original_title else "请分析这个视频"}
                        ]
                    }
                ]

                responses = MultiModalConversation.call(
                    model="qwen-vl-max-latest",
                    messages=messages,
                    stream=True,
                    incremental_output=True,
                    timeout=600  # 增加超时时间到 10 分钟, 适应大文件
                )

                full_content = []
                for response in responses:
                    try:
                        content = response["output"]["choices"][0]["message"]["content"]
                        if content and isinstance(content, list) and "text" in content[0]:
                            text_content = content[0]["text"]
                            full_content.append(text_content)
                    except (KeyError, IndexError) as error:
                        logging.debug(f"解析响应时出错: {error}")
                    except Exception as e:
                        logging.debug(f"未知错误: {e}")

                result_text = ''.join(full_content)
                result = json.loads(result_text)

                if result.get('title') and result.get('tag'):
                    logging.info(f"✅ AI 分析完成")
                    return result
                else:
                    raise ValueError("AI 返回结果格式不正确")

            except Exception as e:
                logging.warning(f"⚠️ AI 分析失败 (第 {attempt} 次): {str(e)}")
                if attempt < max_retries:
                    logging.info(f"等待 {retry_delay} 秒后重试...")
                    # 改用 time.sleep
                    time.sleep(retry_delay)
                else:
                    logging.error(f"❌ AI 分析最终失败: {video_path.name}")

        # 所有重试失败后返回默认值
        return {
            'title': video_path.stem,
            'tag': '生活,日常,分享,有趣,推荐,精彩,热门,必看'
        }


class VideoUploader:
    """视频上传类 (支持人工审核)"""

    def __init__(self, config: StandaloneUploadConfig):
        self.config = config
        self.ai_analyzer = AIAnalyzer(config.DASHSCOPE_API_KEY)

        # 如果启用了 Docker 模拟模式,设置环境变量
        if self.config.DOCKER_MODE:
            os.environ['DOCKER_ENV'] = 'true'
            logging.info("已设置环境变量 DOCKER_ENV=true")

        # 初始化上传历史记录
        self.history_file = Path('logs/uploaded_history.txt')
        self.uploaded_history = self._load_history()

    def scan_video_width(self, video_path: Path) -> int:
        """获取视频宽度
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            int: 视频宽度, 如果获取失败则返回 0
        """
        try:
            with suppress_stderr():
                cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                return 0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            cap.release()
            return width
        except ImportError:
            logging.warning("未安装 opencv-python, 无法获取视频分辨率")
            return 0
        except Exception as e:
            logging.error(f"获取视频宽度失败: {e}")
            return 0

    def _load_history(self) -> set:
        """加载已上传视频的历史记录"""
        history = set()
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            history.add(line)
                logging.info(f"已加载 {len(history)} 条上传历史记录")
            except Exception as e:
                logging.error(f"加载历史记录失败: {e}")
        return history

    def _save_history(self, filename: str):
        """保存上传记录"""
        try:
            # 确保目录存在
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.history_file, 'a', encoding='utf-8') as f:
                f.write(f"{filename}\n")
            self.uploaded_history.add(filename)
        except Exception as e:
            logging.error(f"保存历史记录失败: {e}")

    def fetch_from_nas(self, nas_dir: Path, target_dir: Path):
        """从 NAS 目录拉取视频文件到本地
        
        Args:
            nas_dir: NAS 目录路径
            target_dir: 本地目标目录
        """
        if not nas_dir or not nas_dir.exists():
            logging.warning("NAS 目录未配置或不存在,跳过拉取")
            return

        logging.info(f"正在从 NAS 拉取视频: {nas_dir} -> {target_dir}")

        # 查找所有 .mp4 文件
        video_files = list(nas_dir.glob('*.mp4'))
        if not video_files:
            logging.info("NAS 目录中未找到视频文件")
            return

        count = 0
        for video_file in video_files:
            if count >= 1:
                logging.info("已达到单次拉取数量限制(1个),停止拉取")
                break

            # 处理文件名: 去除特殊符号和空格
            # 保留: 中文, 英文, 数字
            stem = video_file.stem
            suffix = video_file.suffix

            # 使用正则替换非中文、非字母、非数字的字符为空
            new_stem = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', stem)

            # 如果处理后文件名为空(全是特殊符号),则保留原名或使用默认名
            if not new_stem:
                logging.warning(f"文件名清洗后为空: {stem}, 使用原名")
                new_stem = stem

            new_filename = f"{new_stem}{suffix}"

            # 检查是否已上传过
            if new_filename in self.uploaded_history:
                logging.info(f"文件已在上传历史中,跳过: {new_filename}")
                continue

            target_file = target_dir / new_filename

            if not target_file.exists():
                # 获取文件大小 (MB)
                file_size_mb = video_file.stat().st_size / (1024 * 1024)

                # 获取视频宽度
                width = self.scan_video_width(video_file)

                # 自动过滤: 只保留宽度为 720 的视频
                if width != 720:
                    logging.info(f"跳过非 720p 视频: {video_file.name} (宽度: {width})")
                    continue

                logging.info(f"发现符合条件的视频: {video_file.name}")
                logging.info(f"清洗后名: {new_filename}")
                logging.info(f"文件大小: {file_size_mb:.2f} MB")
                logging.info(f"视频宽度: {width}")

                try:
                    logging.info(f"正在复制: {video_file.name} -> {new_filename}")
                    shutil.copy2(video_file, target_file)
                    count += 1
                except Exception as e:
                    logging.error(f"复制失败 {video_file.name}: {e}")

                # 复制成功后直接跳出（因为只需要一个）
                break

            else:
                logging.debug(f"文件已存在,跳过: {new_filename}")

        logging.info(f"✅ 从 NAS 拉取完成,新增 {count} 个视频")

    async def setup_account(self) -> bool:
        """设置账号登录 (支持 cookie 复用 + 验证缓存)"""
        try:
            # 检查账号文件是否存在
            logging.info(f"正在检查账号文件: {self.config.ACCOUNT_FILE.absolute()}")
            if self.config.ACCOUNT_FILE.exists():
                logging.info("检测到已保存的登录状态,正在验证 cookie 有效性...")

                # 验证 cookie 是否有效
                is_valid = await cookie_auth(str(self.config.ACCOUNT_FILE))

                if is_valid:
                    return True
                else:
                    logging.warning("⚠️  Cookie 已失效,需要重新登录")
            else:
                logging.info("未找到登录状态,需要扫码登录")

            # Cookie 不存在或已失效,使用 weixin_setup 进行扫码登录
            logging.info("📱 准备扫码登录")
            logging.info("💡 登录成功后,cookie 将被保存,下次无需重复扫码")
            logging.info("⏰ 请准备好手机微信,浏览器即将打开...")

            # 使用 weixin_setup 进行扫码登录
            # handle=True 会打开浏览器进行扫码

            success = await weixin_setup(str(self.config.ACCOUNT_FILE), handle=True)

            if success:
                logging.info("✅ 扫码登录成功,cookie 已保存")
                return True
            else:
                logging.error("❌ 扫码登录失败")
                return False

        except Exception as e:
            logging.error(f"❌ 账号设置失败: {e}")
            logging.error(traceback.format_exc())
            return False

    def generate_metadata_file(self, video_path: Path) -> Path:
        """为视频生成元数据文件 (标题和标签)
        
        Args:
            video_path: 视频文件路径
        
        Returns:
            元数据文件路径
        """
        metadata_file = video_path.with_suffix('.txt')

        # 如果文件已存在,说明已经生成过或用户已修改,直接返回
        if metadata_file.exists():
            logging.info(f"元数据文件已存在: {metadata_file.name}")
            return metadata_file

        # 先创建文件,写入默认内容
        logging.info(f"正在为 {video_path.name} 生成元数据文件...")
        with open(metadata_file, 'w', encoding='utf-8') as f:
            f.write(f"标题: 正在AI分析中...\n")
            f.write(f"标签: 正在AI分析中...\n")
            f.write("\n")
            f.write("# ========== 使用说明 ==========\n")
            f.write("# 第一行是标题 (格式: 标题: xxx)\n")
            f.write("# 第二行是标签 (格式: 标签: tag1,tag2,tag3)\n")
            f.write("# 请根据视频内容修改标题和标签\n")
            f.write("# 修改完成后保存文件即可\n")
            f.write("# ==============================\n")

        logging.info(
            f"✅"
            f" 已创建元数据文件: {metadata_file.name}"
        )

        # AI 分析视频生成标题和标签
        logging.info(f"AI 分析视频: {video_path.name}")
        ai_result = self.ai_analyzer.analyze_video(video_path)

        # 更新文件内容
        with open(metadata_file, 'w', encoding='utf-8') as f:
            f.write(f"标题: {ai_result['title']}\n")
            f.write(f"标签: {ai_result['tag']}\n")
            f.write("\n")
            f.write("# ========== 使用说明 ==========\n")
            f.write("# 第一行是标题 (格式: 标题: xxx)\n")
            f.write("# 第二行是标签 (格式: 标签: tag1,tag2,tag3)\n")
            f.write("# 请根据视频内容修改标题和标签\n")
            f.write("# 修改完成后保存文件即可\n")
            f.write("# ==============================\n")

        logging.info(f"✅ AI 分析完成,已更新元数据文件")
        logging.info(f"标题: {ai_result['title']}")
        logging.info(f"标签: {ai_result['tag']}")

        return metadata_file

    def read_metadata_file(self, metadata_file: Path) -> Dict[str, any]:
        """读取元数据文件
        
        Args:
            metadata_file: 元数据文件路径
        
        Returns:
            包含 title 和 tags 的字典
        """
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            title = ""
            tags = []

            for line in lines:
                line = line.strip()
                if line.startswith('#') or not line:
                    continue

                if line.startswith('标题:') or line.startswith('标题：'):
                    title = line.split(':', 1)[1].strip() if ':' in line else line.split('：', 1)[1].strip()
                elif line.startswith('标签:') or line.startswith('标签：'):
                    tag_str = line.split(':', 1)[1].strip() if ':' in line else line.split('：', 1)[1].strip()
                    tags = [tag.strip() for tag in tag_str.split(',') if tag.strip()]

            if not title:
                raise ValueError("未找到标题")
            if not tags:
                raise ValueError("未找到标签")

            return {'title': title, 'tags': tags}

        except Exception as e:
            logging.error(f"读取元数据文件失败: {e}")
            raise

    async def upload_single_video(self, video_path: Path, metadata_file: Path) -> bool:
        """上传单个视频
        
        Args:
            video_path: 视频文件路径
            metadata_file: 元数据文件路径
        
        Returns:
            上传是否成功
        """
        try:
            logging.info(f"开始上传: {video_path.name}")

            # 读取元数据文件
            metadata = self.read_metadata_file(metadata_file)
            title = metadata['title']
            tags = metadata['tags']

            logging.info(f"标题: {title}")
            logging.info(f"标签: {', '.join(tags)}")

            # 上传视频
            logging.info("正在上传到视频号...")
            app = TencentVideo(
                title=title,
                file_path=video_path,
                tags=tags,
                publish_date=self.config.PUBLISH_DATE,
                account_file=self.config.ACCOUNT_FILE,
                category=self.config.CATEGORY
            )
            await app.main()

            logging.info(f"✅ 上传成功: {video_path.name}")

            # 上传成功后保存记录并删除视频和元数据文件
            self._save_history(video_path.name)

            if self.config.DELETE_AFTER_UPLOAD:
                video_path.unlink()
                metadata_file.unlink()
                logging.info(f"已删除本地文件: {video_path.name} 和 {metadata_file.name}")

            return True

        except Exception as e:
            logging.error(f"❌ 上传失败: {video_path.name}")
            logging.error(f"错误信息: {e}")
            return False

    def generate_all_metadata(self):
        """为所有视频生成元数据文件"""
        all_video_files = list(self.config.VIDEO_DIR.glob('*.mp4'))

        # 过滤已上传的视频
        video_files = []
        for v in all_video_files:
            if v.name in self.uploaded_history:
                logging.info(f"跳过已上传视频: {v.name}")
            else:
                video_files.append(v)

        if not video_files:
            logging.info("没有需要生成元数据的视频文件")
            return []

        logging.info(f"找到 {len(video_files)} 个视频文件")

        metadata_files = []

        for i, video_file in enumerate(video_files, 1):
            logging.info(f"进度: [{i}/{len(video_files)}]")
            try:
                metadata_file = self.generate_metadata_file(video_file)
                metadata_files.append((video_file, metadata_file))
            except Exception as e:
                logging.error(f"生成元数据失败: {video_file.name} -> {e}")

        return metadata_files

    def notify_qr_login(self):
        """发送扫码登录通知"""
        try:
            notifier = BarkNotifier(config.bark_key)
            notifier.send(
                title="📱 需要扫码登录",
                content="视频号上传工具需扫码登录，请并在控制台按回车继续",
                level="timeSensitive",
                sound="alarm",
                group="视频上传",
                icon="https://api.iconify.design/mdi:qrcode-scan.svg"
            )
        except Exception as e:
            logging.error(f"发送通知失败: {e}")

    def notify_manual_review(self, count):
        """发送人工审核通知"""
        try:
            notifier = BarkNotifier(config.bark_key)
            notifier.send(
                title="📝 等待人工审核",
                content=f"已生成 {count} 个视频的元数据，请审核后在控制台按回车继续",
                sound="minuet",
                group="视频上传",
                icon="https://api.iconify.design/mdi:file-document-edit-outline.svg"
            )
        except Exception as e:
            logging.error(f"发送通知失败: {e}")

    def notify_completion(self, count, success, fail):
        """发送完成通知"""
        try:
            notifier = BarkNotifier(config.bark_key)
            notifier.send(
                title="📤 视频上传完成",
                content=f"总计: {count} | 成功: {success} | 失败: {fail}",
                group="视频上传",
                sound="fanfare",
                icon="https://api.iconify.design/mdi:cloud-upload-outline.svg"
            )
        except Exception as e:
            logging.error(f"发送通知失败: {e}")

    async def upload_all_videos(self):
        """上传所有视频 (优化后的流程)"""

        # 第一步: 账号登录 (智能登录)
        logging.info("【第一步】账号登录")
        # 发送扫码提醒(如果需要的话)
        if not self.config.ACCOUNT_FILE.exists():
            self.notify_qr_login()

        if not await self.setup_account():
            logging.error("❌ 登录失败,无法继续上传")
            logging.error("请检查网络连接或稍后重试")
            return

        # 第二步: 从 NAS 拉取视频
        if self.config.NAS_DIR:
            logging.info("【第二步】从 NAS 拉取视频")

            # 检查本地是否已有待上传的视频 (MP4 + TXT)
            existing_videos = list(self.config.VIDEO_DIR.glob('*.mp4'))
            pending_videos = []
            for v in existing_videos:
                metadata_path = v.with_suffix('.txt')
                if metadata_path.exists() and v.name not in self.uploaded_history:
                    pending_videos.append(v)

            if pending_videos:
                logging.info(f"本地已有 {len(pending_videos)} 个待上传视频 (已含元数据), 跳过从 NAS 拉取")
                for v in pending_videos:
                    logging.info(f"  - {v.name}")
            else:
                self.fetch_from_nas(self.config.NAS_DIR, self.config.VIDEO_DIR)

        # 第三步: 生成所有元数据文件
        logging.info("【第三步】生成元数据文件")
        metadata_files = self.generate_all_metadata()
        if not metadata_files:
            logging.info("没有需要上传的视频文件")
            return
        # 第四步: 等待用户审核
        logging.info("【第四步】人工审核")
        logging.info(f"✅ 已为 {len(metadata_files)} 个视频生成元数据文件")
        logging.info(f"📁 元数据文件位置: {self.config.VIDEO_DIR}")
        logging.info("📝 请检查并修改每个视频对应的 .txt 文件:")
        for video_file, metadata_file in metadata_files:
            logging.info(f"{metadata_file.name}")
        logging.info("⚠️  请根据实际视频内容修改标题和标签!")
        logging.info("✅ 修改完成后,按回车键继续上传...")
        # 发送审核提醒
        self.notify_manual_review(len(metadata_files))

        # 第五步: 批量上传
        logging.info("【第五步】批量上传")

        # 再次检查登录状态 (防止在人工审核期间 session 过期)
        logging.info("正在验证登录状态...")
        if not await self.setup_account():
            logging.error("❌ 登录验证失败/已过期,且重新登录失败,无法继续")
            return

        logging.info(f"📤 开始上传 {len(metadata_files)} 个视频...")
        success_count = 0
        fail_count = 0
        for i, (video_file, metadata_file) in enumerate(metadata_files, 1):
            logging.info(f"进度: [{i}/{len(metadata_files)}]")

            try:
                result = await self.upload_single_video(video_file, metadata_file)
                if result:
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                fail_count += 1
                logging.error(f"上传异常: {e}")

            logging.info(f"当前统计 - 成功: {success_count}, 失败: {fail_count}")

        logging.info("上传完成!")
        logging.info(f"总计: {len(metadata_files)} 个文件")
        logging.info(f"成功: {success_count} 个")
        logging.info(f"失败: {fail_count} 个")

        # 发送完成提醒
        self.notify_completion(len(metadata_files), success_count, fail_count)


async def main():
    """主函数"""
    try:
        logging.info("独立视频号上传工具启动")

        # 初始化配置
        config = StandaloneUploadConfig()

        # 创建上传器
        uploader = VideoUploader(config)

        # 执行上传
        await uploader.upload_all_videos()

    except KeyboardInterrupt:
        logging.info("\n用户中断,程序退出")
    except Exception as e:
        logging.error(f"程序执行失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
