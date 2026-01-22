# -*- coding: utf-8 -*-
"""
抖音设备ID和Token刷新脚本
用于生成新的msToken、ttwid和webid
"""

import os
import sys
import asyncio
from ruamel.yaml import YAML

async def main():
    """
    刷新抖音的msToken、ttwid和webid
    """
    print("=" * 50)
    print("抖音设备ID刷新工具")
    print("=" * 50)
    print()
    
    try:
        from f2.apps.douyin.utils import TokenManager
        
        print("正在生成msToken...")
        try:
            msToken = TokenManager.gen_real_msToken()
            print(f"✅ msToken: {msToken[:20]}...")
        except Exception as e:
            print(f"⚠️ 生成真实msToken失败,使用虚假msToken: {e}")
            msToken = TokenManager.gen_false_msToken()
            print(f"✅ 虚假msToken: {msToken[:20]}...")
        
        print("\n正在生成ttwid...")
        try:
            ttwid = TokenManager.gen_ttwid()
            print(f"✅ ttwid: {ttwid[:20]}...")
        except Exception as e:
            print(f"❌ 生成ttwid失败: {e}")
            ttwid = None
        
        print("\n正在生成webid...")
        try:
            webid = TokenManager.gen_webid()
            print(f"✅ webid: {webid}")
        except Exception as e:
            print(f"❌ 生成webid失败: {e}")
            webid = None
        
        # 初始化ruamel.yaml实例
        yaml = YAML()
        yaml.preserve_quotes = True
        
        # 更新 my_apps.yaml 中的Cookie
        apps_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'my_apps.yaml')
        
        print(f"\n正在更新配置文件: {apps_path}")
        
        try:
            with open(apps_path, "r", encoding='utf-8') as f:
                data = yaml.load(f) or {}
            
            # 获取现有Cookie
            existing_cookie = data.setdefault('douyin', {}).get('cookie', '')
            
            # 解析现有Cookie为字典
            cookie_dict = {}
            if existing_cookie:
                cookie_dict = dict(
                    item.strip().split('=', 1)
                    for item in existing_cookie.split(';')
                    if '=' in item.strip()
                )
            
            # 更新Token
            if msToken:
                cookie_dict['msToken'] = msToken
            if ttwid:
                cookie_dict['ttwid'] = ttwid
            if webid:
                cookie_dict['__ac_nonce'] = webid  # webid通常存储在__ac_nonce中
            
            # 重新组合Cookie
            data['douyin']['cookie'] = '; '.join(f"{k}={v}" for k, v in cookie_dict.items())
            
            with open(apps_path, "w", encoding='utf-8') as f:
                yaml.dump(data, f)
            
            print(f"✅ 已更新配置文件")
            print(f"✅ 设备ID刷新成功!")
            print()
            print("=" * 50)
            print("提示:")
            print("1. msToken和ttwid已更新到配置文件")
            print("2. 如果采集仍然失败,请重新获取完整的Cookie")
            print("3. 运行 'python main.py' 开始采集")
            print("=" * 50)
            
        except Exception as e:
            print(f"❌ 更新配置文件失败: {e}")
            print("\n生成的Token:")
            if msToken:
                print(f"msToken={msToken}")
            if ttwid:
                print(f"ttwid={ttwid}")
            if webid:
                print(f"webid={webid}")
            print("\n请手动将上述Token添加到 my_apps.yaml 的 douyin.cookie 中")
    
    except ImportError as e:
        print(f"❌ 导入f2模块失败: {e}")
        print("\n请确保已安装f2:")
        print("pip install f2")
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
