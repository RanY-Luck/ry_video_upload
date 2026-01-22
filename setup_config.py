"""
快速配置向导 - .env 版本
帮助用户快速创建和配置 .env 文件
"""
import sys
from pathlib import Path
from Upload.utils.config_loader import config

def print_banner():
    """打印欢迎横幅"""
    print("=" * 60)
    print("视频搬运工具 - 快速配置向导")
    print("=" * 60)
    print()


def check_env_exists():
    """检查 .env 文件是否存在"""
    env_file = Path(__file__).parent / '.env'
    return env_file.exists()


def create_env_from_example():
    """从示例文件创建 .env 文件"""
    example_file = Path(__file__).parent / '.env.example'
    env_file = Path(__file__).parent / '.env'
    
    if not example_file.exists():
        print("❌ 错误: 找不到 .env.example 文件")
        return False
    
    try:
        with open(example_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        with open(env_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ 已创建 .env 文件")
        return True
    except Exception as e:
        print(f"❌ 创建配置文件失败: {e}")
        return False


def get_user_input(prompt, default=""):
    """获取用户输入"""
    if default:
        user_input = input(f"{prompt} [{default}]: ").strip()
        return user_input if user_input else default
    else:
        while True:
            user_input = input(f"{prompt}: ").strip()
            if user_input:
                return user_input
            print("⚠️  此项为必填项，请输入有效值")


def update_env_value(lines, key, value):
    """更新 .env 文件中的值
    
    Args:
        lines: 配置文件行列表
        key: 环境变量名
        value: 新值
    
    Returns:
        更新后的行列表
    """
    for i, line in enumerate(lines):
        stripped = line.strip()
        # 跳过注释和空行
        if not stripped or stripped.startswith('#'):
            continue
        # 检查是否匹配目标键
        if '=' in stripped and stripped.split('=')[0].strip() == key:
            lines[i] = f'{key}={value}\n'
            break
    return lines


def configure_interactive():
    """交互式配置"""
    print("\n开始配置...")
    print("-" * 60)
    
    env_file = Path(__file__).parent / '.env'
    
    # 读取 .env 文件
    with open(env_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 1. 配置抖音目标用户 URL
    print("\n【1/3】配置抖音目标用户")
    print("说明: 打开抖音用户主页，复制完整 URL")
    print("示例: https://www.douyin.com/user/MS4wLjABAAAA0r-B3uubLdhDTB1PuYZ-uKtjoD86_b1aW8HzG-G0DRg")
    target_url = get_user_input("请输入抖音目标用户 URL")
    lines = update_env_value(lines, 'DOUYIN_TARGET_URL', target_url)
    
    # 2. 配置阿里云百炼 API Key
    print("\n【2/3】配置阿里云百炼 API Key")
    print("说明: 访问 https://bailian.console.aliyun.com/ 获取 API Key")
    print("用途: AI 自动生成视频标题和标签")
    api_key = get_user_input("请输入阿里云百炼 API Key")
    lines = update_env_value(lines, 'DASHSCOPE_API_KEY', api_key)
    
    # 3. 配置调度间隔
    print("\n【3/3】配置调度间隔")
    print("说明: 设置视频采集的时间间隔 (单位: 分钟)")
    print("建议: 5-60 分钟，避免过于频繁被检测为爬虫")
    interval = get_user_input("请输入调度间隔", "300")
    lines = update_env_value(lines, 'SCHEDULE_INTERVAL', interval)
    
    # 写回 .env 文件
    with open(env_file, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print("\n✅ 配置已保存到 .env")


def Test_config():
    """测试配置加载"""
    print("\n测试配置加载...")
    print("-" * 60)
    
    try:

        
        print(f"✅ 抖音目标 URL: {config.douyin_target_url}")
        print(f"✅ API Key: {config.dashscope_api_key[:20]}...")
        print(f"✅ 调度间隔: {config.schedule_interval} 分钟")
        print(f"✅ 时区: {config.timezone}")
        print(f"✅ 最大线程数: {config.max_workers}")
        
        print("\n✅ 配置加载成功!")
        return True
    except Exception as e:
        print(f"\n❌ 配置加载失败: {e}")
        print("\n请检查:")
        print("1. .env 文件是否存在")
        print("2. 配置项是否填写正确")
        print("3. 是否有语法错误")
        return False


def main():
    """主函数"""
    print_banner()
    
    # 检查 .env 文件是否存在
    if check_env_exists():
        print("⚠️  检测到 .env 已存在")
        choice = input("是否要重新配置? (y/N): ").strip().lower()
        if choice != 'y':
            print("\n已取消配置")
            return
    else:
        print("未检测到 .env 文件，将创建新配置")
    
    # 创建 .env 文件
    if not create_env_from_example():
        return
    
    # 交互式配置
    configure_interactive()
    
    # 测试配置
    if Test_config():
        print("\n" + "=" * 60)
        print("配置完成! 现在可以运行程序:")
        print("  - 完整流程: python main.py")
        print("  - 独立去重: python standalone_dedup.py")
        print("  - 独立上传: python standalone_upload.py")
        print("=" * 60)
    else:
        print("\n⚠️  配置测试失败，请检查 .env 文件")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n用户中断，配置已取消")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
