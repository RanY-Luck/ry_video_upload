"""
通用工具模块
提供路径配置、日志配置等通用功能
"""
import sys
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler


def setup_project_paths():
    """设置项目路径
    
    将项目根目录和 Upload 目录添加到 Python 路径中
    必须在导入其他项目模块之前调用
    """
    project_root = Path(__file__).parent
    upload_dir = project_root / 'Upload'

    # 添加到 sys.path（如果还未添加）
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    if str(upload_dir) not in sys.path:
        sys.path.insert(0, str(upload_dir))


def setup_logging(
        log_file: str = 'app.log',
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5,
        level: int = logging.INFO
):
    """配置日志系统
    
    Args:
        log_file: 日志文件名
        max_bytes: 单个日志文件最大大小（字节）
        backup_count: 保留的日志文件数量
        level: 日志级别
    
    Returns:
        配置好的 logger 实例
    """
    # 确保日志文件所在的目录存在
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # 创建文件处理器
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )

    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)

    # 设置格式
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # 配置根日志器
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[file_handler, console_handler]
    )

    return logging.getLogger()


def get_project_root() -> Path:
    """获取项目根目录

    Returns:
        项目根目录的绝对路径
    """
    return Path(__file__).parent.resolve()


def get_upload_dir() -> Path:
    """获取 Upload 目录

    Returns:
        Upload 目录的绝对路径
    """
    return get_project_root() / 'Upload'


if __name__ == "__main__":
    # 测试工具函数
    print("=" * 60)
    print("通用工具模块测试")
    print("=" * 60)

    # 测试路径设置
    setup_project_paths()
    print(f"✅ 项目路径已设置")
    print(f"   项目根目录: {get_project_root()}")
    print(f"   Upload 目录: {get_upload_dir()}")

    # 测试日志配置
    logger = setup_logging('test.log')
    logger.info("✅ 日志系统已配置")
    logger.info("   日志文件: test.log")

    print("\n✅ 所有测试通过!")