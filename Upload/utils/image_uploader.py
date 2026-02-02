# -*- coding: utf-8 -*-
"""
图片上传工具模块
支持 ImgBB 等图床上传
"""
import base64
import httpx
from typing import Optional
from Upload.utils.log import tencent_logger
from Upload.utils.config_loader import config


class ImageUploader:
    """图片上传类"""

    @staticmethod
    async def upload_to_imgbb(image_data: bytes, api_key: str = None) -> Optional[str]:
        """
        上传图片到 imgbb 图床

        Args:
            image_data: 图片二进制数据
            api_key: imgbb API Key (如果未提供，尝试从配置获取)

        Returns:
            公网可访问的图片 URL
        """
        if not api_key:
            api_key = config.get('IMGBB_API_KEY')

        if not api_key:
            tencent_logger.warning("未配置 IMGBB_API_KEY，无法上传图片")
            return None

        tencent_logger.info("正在上传图片到 imgbb 图床...")

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                # imgbb 需要 base64 编码
                image_base64 = base64.b64encode(image_data).decode('utf-8')

                response = await client.post(
                    "https://api.imgbb.com/1/upload",
                    data={
                        'key': api_key,
                        'image': image_base64,
                        'name': 'wechat_screenshot'
                    }
                )

                result = response.json()

                if result.get('success'):
                    url = result['data']['url']
                    tencent_logger.info(f"图片上传成功: {url}")
                    return url
                else:
                    tencent_logger.error(f"imgbb 上传失败: {result}")
                    return None

        except Exception as e:
            tencent_logger.error(f"imgbb 上传异常: {e}")
            return None
