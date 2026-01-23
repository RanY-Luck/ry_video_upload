#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Bark 通知服务封装模块
"""

import requests
from typing import Optional
from Upload.utils.config_loader import config


class BarkNotifier:
    """Bark 推送通知类"""

    def __init__(self, bark_key:str,bark_server: str = "https://api.day.app"):
        """
        初始化 Bark 推送器
        
        Args:
            bark_server: Bark 服务器地址，默认使用官方服务器
        """
        self.bark_key = config.bark_key
        self.bark_server = bark_server.rstrip('/')

    def send(
            self,
            title: str,
            content: str = "",
            subtitle: Optional[str] = None,
            group: Optional[str] = None,
            icon: Optional[str] = None,
            image: Optional[str] = None,
            sound: Optional[str] = None,
            level: Optional[str] = None,
            volume: Optional[int] = None,
            call: Optional[int] = None,
            url: Optional[str] = None,
            copy: Optional[str] = None,
            auto_copy: Optional[int] = None,
            badge: Optional[int] = None,
            markdown: Optional[int] = None,
            is_archive: Optional[int] = None,
            notification_id: Optional[str] = None,
            action: Optional[str] = None
    ) -> bool:
        """
        发送 Bark 推送通知
        
        Args:
            title: 推送标题
            content: 推送内容（body）
            subtitle: 推送副标题（可选）
            group: 推送分组（可选）
            icon: 推送图标 URL（可选）
            image: 推送图片 URL（可选）
            sound: 推送声音（可选），如 "alarm", "minuet", "bell" 等
            level: 中断级别（可选）："active", "timeSensitive", "passive", "critical"
            volume: 音量（可选），0-10，用于 critical 级别
            call: 持续响铃（可选），设为 1 类似来电效果
            url: 点击推送时打开的 URL（可选）
            copy: 复制到剪贴板的内容（可选）
            auto_copy: 自动复制 content 到剪贴板（可选），设为 1
            badge: App 角标数字（可选）
            markdown: 启用 Markdown 渲染（可选），设为 1
            is_archive: 归档消息（可选），设为 1
            notification_id: 通知 ID（可选），用于更新或替换之前的通知
            action: 设为 "none" 不弹出通知（仅在通知中心显示）
        
        Returns:
            bool: 推送是否成功
        """
        # 构建推送 URL
        push_url = f"{self.bark_server}/{self.bark_key}/{title}"
        if content:
            push_url += f"/{content}"

        # 构建请求参数
        params = {}
        if subtitle:
            params['subtitle'] = subtitle
        if group:
            params['group'] = group
        if icon:
            params['icon'] = icon
        if image:
            params['image'] = image
        if sound:
            params['sound'] = sound
        if level:
            params['level'] = level
        if volume is not None:
            params['volume'] = volume
        if call is not None:
            params['call'] = call
        if url:
            params['url'] = url
        if copy:
            params['copy'] = copy
        if auto_copy is not None:
            params['autoCopy'] = auto_copy
        if badge is not None:
            params['badge'] = badge
        if markdown is not None:
            params['markdown'] = markdown
        if is_archive is not None:
            params['isArchive'] = is_archive
        if notification_id:
            params['id'] = notification_id
        if action:
            params['action'] = action

        try:
            # 发送 GET 请求
            response = requests.get(push_url, params=params, timeout=10)

            # 调试输出（可选，如果需要静默模式可以注释掉）
            # print(f"📡 实际请求 URL: {response.url}")

            response.raise_for_status()

            result = response.json()
            if result.get('code') == 200:
                return True
            else:
                print(f"❌ Bark 推送失败: {result.get('message', '未知错误')}")
                return False

        except requests.exceptions.RequestException as e:
            print(f"❌ Bark 推送请求失败: {e}")
            return False


if __name__ == '__main__':
    notifier = BarkNotifier(config.bark_key)
    notifier.send("测试标题", "这是一条测试消息ranyong")
