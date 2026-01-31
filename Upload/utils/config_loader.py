"""
统一配置加载模块
负责加载和解析 .env 配置文件
"""
import os
from pathlib import Path
from typing import Any
from dotenv import load_dotenv, find_dotenv

from Upload.utils.log import tencent_logger


class ConfigLoader:
    """配置加载器 - 从 .env 文件加载环境变量"""

    _instance = None
    _loaded = False

    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化配置加载器"""
        if not self._loaded:
            self._load_env()
            self._loaded = True

    def _load_env(self):
        """加载 .env 文件"""

        # find_dotenv() 会自动向上查找 .env 文件
        env_file = find_dotenv()

        if not env_file:
            raise FileNotFoundError(
                "未找到 .env 配置文件\n"
                "请在项目根目录创建 .env 文件:\n"
                "  copy .env.example .env\n"
                "然后编辑 .env 文件填写配置"
            )

        load_dotenv(env_file)
        tencent_logger.info(f"✓ 已加载配置文件: {env_file}")

        # 手动解析 .env 文件（避免依赖 python-dotenv）
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # 跳过注释和空行
                if not line or line.startswith('#'):
                    continue
                # 解析键值对
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    # 设置环境变量
                    os.environ[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项
        
        Args:
            key: 环境变量名
            default: 默认值
        
        Returns:
            配置值
        """
        return os.getenv(key, default)

    def get_int(self, key: str, default: int = 0) -> int:
        """获取整数配置项
        
        Args:
            key: 环境变量名
            default: 默认值
        
        Returns:
            整数配置值
        """
        value = os.getenv(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        """获取布尔配置项
        
        Args:
            key: 环境变量名
            default: 默认值
        
        Returns:
            布尔配置值
        """
        value = os.getenv(key)
        if value is None:
            return default
        return value.lower() in ('true', 'yes', '1', 'on')

    def get_required(self, key: str) -> str:
        """获取必需的配置项,如果不存在则抛出异常
        
        Args:
            key: 环境变量名
        
        Returns:
            配置值
        
        Raises:
            ValueError: 配置项不存在或为空
        """
        value = os.getenv(key)
        if not value or value == "YOUR_TARGET_USER_ID" or value == "YOUR_DASHSCOPE_API_KEY":
            raise ValueError(
                f"必需的配置项不存在或未设置: {key}\n"
                f"请编辑 .env 文件并设置正确的值"
            )
        return value

    @property
    def douyin_target_url(self) -> str:
        """抖音目标用户 URL"""
        return self.get_required('DOUYIN_TARGET_URL')

    @property
    def dashscope_api_key(self) -> str:
        """阿里云百炼 API Key"""
        return self.get_required('DASHSCOPE_API_KEY')

    @property
    def schedule_interval(self) -> int:
        """调度间隔 (分钟)"""
        return self.get_int('SCHEDULE_INTERVAL', 300)

    @property
    def timezone(self) -> str:
        """时区"""
        return self.get('TIMEZONE', 'Asia/Shanghai')

    @property
    def max_workers(self) -> int:
        """最大工作线程数"""
        workers = self.get_int('MAX_WORKERS', 0)
        return workers if workers > 0 else os.cpu_count()

    @property
    def upload_category(self) -> str:
        """视频分类"""
        return self.get('VIDEO_CATEGORY', 'CUTE_PETS')


    @property
    def delete_after_upload(self) -> bool:
        """上传后是否删除"""
        return self.get_bool('DELETE_AFTER_UPLOAD', False)

    def get_path(self, key: str) -> Path:
        """获取路径配置
        
        Args:
            key: 路径配置键
        
        Returns:
            绝对路径
        """
        base_dir = Path(__file__).parent.parent.resolve()

        # 路径映射
        paths = {
            'download_dir': 'Download/douyin/post',
            'dedup_dir': 'Dedup',
            'upload_dir': 'Upload',
            'video_output_dir': 'videos',
            'account_file': 'cookies/tencent_uploader/account.json'
        }

        relative_path = paths.get(key)
        if relative_path is None:
            raise ValueError(f"未知的路径配置键: {key}")

        return (base_dir / relative_path).resolve()

    @property
    def bark_key(self) -> str:
        """bark 推送"""
        return self.get_required('BARK_KEY')

    @property
    def dedup_source_dir(self) -> Path:
        """去重源目录 (支持 NAS 路径)"""
        path_str = self.get('DEDUP_SOURCE_DIR')
        if path_str:
            return Path(path_str)
        return None

    @property
    def nas_dir(self) -> Path:
        """NAS 视频素材目录"""
        path_str = self.get('NAS_DIR')
        if path_str:
            return Path(path_str)
        return None

    @property
    def docker_mode(self) -> bool:
        """是否强制启用 Docker 模式 (Bark 扫码)"""
        return self.get_bool('DOCKER_MODE', False)



# 全局配置实例
config = ConfigLoader()

if __name__ == "__main__":
    # 测试配置加载
    print("=" * 60)
    print("配置加载测试")
    print("=" * 60)

    try:
        print(f"抖音目标 URL: {config.douyin_target_url}")
        print(f"API Key: {config.dashscope_api_key[:20]}...")
        print(f"调度间隔: {config.schedule_interval} 分钟")
        print(f"时区: {config.timezone}")
        print(f"最大线程数: {config.max_workers}")
        print(f"视频分类: {config.upload_category}")
        print(f"上传后删除: {config.delete_after_upload}")

        print("\n路径配置:")
        print(f"下载目录: {config.get_path('download_dir')}")
        print(f"去重目录: {config.get_path('dedup_dir')}")
        print(f"上传目录: {config.get_path('upload_dir')}")
        print(f"视频输出目录: {config.get_path('video_output_dir')}")

        print("\n✅ 配置加载成功!")
    except Exception as e:
        print(f"\n❌ 配置加载失败: {e}")
