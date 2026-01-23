"""
独立视频去重工具
功能:扫描 Download/ 目录下的所有 MP4 文件并进行去重处理
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import List
from Upload.utils.log import logger as logging
from Upload.utils.utils_common import setup_logging
from Upload.utils.bark_notifier import BarkNotifier
from Upload.utils.config_loader import config

# 配置日志
logger = setup_logging('logs/standalone_dedup.log')


class StandaloneDedupConfig:
    """独立去重工具配置类"""

    def __init__(self):
        base_dir = Path(__file__).parent.resolve()

        # 目录配置
        self.DOWNLOAD_DIR = (base_dir / 'Download').resolve()
        self.DEDUP_DIR = (base_dir / 'Dedup').resolve()
        self.UPLOAD_DIR = (base_dir / 'Upload').resolve()
        self.DEDUP_SCRIPT = (base_dir / 'Dedup/dedup.py').resolve()

        # 处理记录文件
        self.PROCESSED_LOG = self.DEDUP_DIR / 'logs/processed_videos.log'

        # 线程配置
        self.MAX_WORKERS = os.cpu_count() or 4

        # 验证路径
        self._validate_paths()

    def _validate_paths(self):
        """验证必要的路径是否存在"""
        # 自动创建目录
        for directory in [self.DOWNLOAD_DIR, self.DEDUP_DIR, self.UPLOAD_DIR]:
            directory.mkdir(parents=True, exist_ok=True)

        # 创建日志目录
        self.PROCESSED_LOG.parent.mkdir(parents=True, exist_ok=True)

        # 检查去重脚本
        if not self.DEDUP_SCRIPT.exists():
            raise FileNotFoundError(f"去重脚本不存在: {self.DEDUP_SCRIPT}")

        logging.info(f"下载目录: {self.DOWNLOAD_DIR}")
        logging.info(f"去重脚本: {self.DEDUP_SCRIPT}")
        logging.info(f"输出目录: {self.UPLOAD_DIR / 'videos'}")


class StandaloneDedupProcessor:
    """独立去重处理器"""

    def __init__(self, config: StandaloneDedupConfig):
        self.config = config
        self.processed_files = self._load_processed_files()

    def _load_processed_files(self) -> set:
        """加载已处理文件记录"""
        processed = set()
        if self.config.PROCESSED_LOG.exists():
            with open(self.config.PROCESSED_LOG, 'r', encoding='utf-8') as f:
                processed = set(line.strip() for line in f if line.strip())
        logging.info(f"已加载 {len(processed)} 条处理记录")
        return processed

    def _save_processed_file(self, file_path: str):
        """保存已处理文件记录"""
        with open(self.config.PROCESSED_LOG, 'a', encoding='utf-8') as f:
            f.write(f"{file_path}\n")

    def find_all_mp4_files(self) -> List[Path]:
        """递归查找 Download 目录下所有未处理的 MP4 文件"""
        all_mp4_files = []

        logging.info(f"开始扫描目录: {self.config.DOWNLOAD_DIR}")

        # 递归查找所有 .mp4 文件
        for mp4_file in self.config.DOWNLOAD_DIR.rglob('*.mp4'):
            if mp4_file.is_file():
                # 检查是否已处理
                if str(mp4_file) not in self.processed_files:
                    all_mp4_files.append(mp4_file)
                else:
                    logging.debug(f"跳过已处理文件: {mp4_file.name}")

        logging.info(f"找到 {len(all_mp4_files)} 个未处理的 MP4 文件")
        return all_mp4_files

    def process_single_video(self, input_file: Path) -> bool:
        """处理单个视频文件"""
        output_dir = self.config.UPLOAD_DIR / 'videos'
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / input_file.name

        try:
            logging.info("=" * 60)
            logging.info(f"开始处理: {input_file.name}")
            logging.info(f"输入文件: {input_file}")
            logging.info(f"输出文件: {output_file}")
            logging.info("=" * 60)

            # 让 FFmpeg 的输出直接显示到控制台
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(self.config.DEDUP_SCRIPT),
                    "-i", str(input_file),
                    "-o", str(output_file)
                ],
                cwd=self.config.DEDUP_DIR,
                stdout=None,  # 直接输出到控制台
                stderr=None,  # 直接输出到控制台
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
            )

            process.wait()

            if process.returncode == 0:
                logging.info("=" * 60)
                logging.info(f"✅ 去重成功: {input_file.name}")
                logging.info("=" * 60)
                self._save_processed_file(str(input_file))
                return True
            else:
                logging.error("=" * 60)
                logging.error(f"❌ 去重失败: {input_file.name}, 返回码: {process.returncode}")
                logging.error("=" * 60)
                return False

        except Exception as e:
            logging.error("=" * 60)
            logging.error(f"❌ 处理视频异常: {input_file.name} -> {e}")
            logging.error("=" * 60)
            return False

    async def notify_completion(self, count, success, fail):
        """发送完成通知"""
        import asyncio
        try:
            notifier = BarkNotifier(config.bark_key)
            await asyncio.to_thread(
                notifier.send,
                title="🎬 视频去重完成",
                content=f"总计: {count} | 成功: {success} | 失败: {fail}",
                group="视频处理",
                sound="glass",
                icon="https://api.iconify.design/mdi:layers-triple-outline.svg"
            )
        except Exception as e:
            logging.error(f"发送通知失败: {e}")

    def process_all_videos(self):
        """顺序处理所有视频 (单线程,可看到实时进度)"""
        mp4_files = self.find_all_mp4_files()

        if not mp4_files:
            logging.info("没有需要处理的视频文件")
            return

        logging.info("=" * 60)
        logging.info(f"开始处理,共 {len(mp4_files)} 个视频文件")
        logging.info("=" * 60)

        success_count = 0
        fail_count = 0

        # 单线程顺序处理,可以看到每个视频的实时进度
        for i, video_file in enumerate(mp4_files, 1):
            logging.info(f"\n进度: [{i}/{len(mp4_files)}]")

            try:
                result = self.process_single_video(video_file)
                if result:
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                fail_count += 1
                logging.error(f"任务执行异常: {e}")

            logging.info(f"当前统计 - 成功: {success_count}, 失败: {fail_count}")

        logging.info("\n" + "=" * 60)
        logging.info("处理完成!")
        logging.info(f"总计: {len(mp4_files)} 个文件")
        logging.info(f"成功: {success_count} 个")
        logging.info(f"失败: {fail_count} 个")
        logging.info("=" * 60)

        # 发送通知
        import asyncio
        try:
            asyncio.run(self.notify_completion(len(mp4_files), success_count, fail_count))
        except Exception:
            # 如果已有 loop 正在运行 (极少情况), 退化为同步调用或者忽略
            notifier = BarkNotifier(config.bark_key)
            notifier.send(
                title="🎬 视频去重完成",
                content=f"总计: {len(mp4_files)} | 成功: {success_count} | 失败: {fail_count}",
                group="视频处理",
                sound="glass"
            )


def main():
    """主函数"""
    try:
        logging.info("=" * 50)
        logging.info("独立视频去重工具启动")
        logging.info("=" * 50)

        # 初始化配置
        init_config = StandaloneDedupConfig()

        # 创建处理器
        processor = StandaloneDedupProcessor(init_config)

        # 执行去重
        processor.process_all_videos()

    except KeyboardInterrupt:
        logging.info("\n用户中断,程序退出")
    except Exception as e:
        logging.error(f"程序执行失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
