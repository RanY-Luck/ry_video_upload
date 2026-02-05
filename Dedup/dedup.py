
import os
import re
import math
import cv2
import opencc
import tempfile
import random
import logging
import numpy as np
import pysrt
import whisper
import argparse
from typing import List, Tuple, Generator
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw, ImageFont

# 配置 FFmpeg 路径（Windows 系统）
FFMPEG_PATHS = [
    r'D:\ffmpeg\bin',
    r'C:\ffmpeg\bin',
    os.path.expanduser(r'~\ffmpeg\bin'),
]
for ffmpeg_path in FFMPEG_PATHS:
    if os.path.exists(ffmpeg_path) and ffmpeg_path not in os.environ.get('PATH', ''):
        os.environ['PATH'] = ffmpeg_path + os.pathsep + os.environ.get('PATH', '')
        break

# 在设置 PATH 后再导入依赖 ffmpeg 的模块
import ffmpeg
from pydub import AudioSegment
from pydub.silence import split_on_silence

# 配置日志记录，用于调试和监控程序运行状态
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class VideoConfig:
    """
    视频配置类，用于管理音频、视频特效、字幕等参数。
    """
    def __init__(self):
        # GPU加速
        self.enable_gpu: bool = True  # 是否启用 GPU 加速

        # 视频加速与随机镜像
        self.enable_speed_change: bool = True               # 是否启用视频加速
        self.speed_change_range: tuple = (1.05, 1.15)       # 随机加速范围
        self.enable_random_flip: bool = False               # 是否启用随机水平镜像（覆盖 flip_horizontal） - 设为False以强制使用flip_horizontal

        # 字幕参数
        self.include_subtitles: bool = False                # 是否添加字幕
        self.subtitles_opacity: float = 0.10                # 字幕透明度，范围0-1，默认1.0
        self.use_whisper: bool = True                       # 是否使用 Whisper 自动生成字幕
        self.whisper_model_name: str = 'base'               # 默认使用 'base' 模型
        self.subtitles_file: str = 'assets/subtitles.srt'   # 字幕文件路径
        self.subtitles_color: str = 'yellow'                # 字幕字体颜色
        self.subtitles_duration: int = 5                    # 字幕持续时间（秒），视频时长超过此值时添加字幕。

        # 标题参数
        self.include_titles: bool = True                   # 是否添加标题
        self.titles_opacity: float = 0.8                   # 标题透明度，范围0-1，建议 0.5-1.0
        self.top_title: str = '@暖心守护人'                       # 顶部标题文本
        self.top_title_margin: int = 5                      # 顶部标题与顶部的间隙百分比，范围 0-100。
        self.bottom_title: str = ''                    # 底部标题文本
        self.bottom_title_margin: int = 5                   # 底部标题与底部的间隙百分比，范围 0-100。
        self.titles_color: str = 'red'                      # 标题颜色，支持颜色名称或 HEX 码。

        # 水印参数
        self.include_watermark: bool = True                         # 是否添加水印
        self.watermark_opacity: float = 0.1                         # 水印透明度，范围0-1，建议 0.10-0.20
        self.watermark_direction: str = 'center'                    # 水印移动方向:random(每帧随机位置)、left_to_right(从左到右水平移动)、right_to_left(从右到左水平移动)、top_to_bottom(从上到下垂直移动)、bottom_to_top(从下到上垂直移动)、lt_to_rb(左上到右下对角线)、rt_to_lb(右上到左下对角线)、lb_to_rt(左下到右上对角线)、rb_to_lt(右下到左上对角线)
        self.watermark_color: str = 'white'                         # 水印颜色，支持颜色名称或 HEX 码。
        self.watermark_text: str = '@暖心守护人'                    # 水印文本内容
        self.watermark_type: str = 'text'                           # 水印类型，根据类型设置对应路径，text、image、video。
        self.watermark_image_path: str = 'assets/watermark.png'     # 图片水印文件路径，当 watermark_type 为 'image' 时使用。
        self.watermark_video_path: str = ''                         # 视频水印文件路径，当 watermark_type 为 'video' 时使用。

        # 字体
        self.custom_font_enabled: bool = True               # 是否使用自定义字体
        self.font_file: str = 'assets/fonts/simkai.ttf'     # 字体文件路径

        # 文字外边框
        self.text_border_size: int = 1                      # 文字外边框像素大小

        # 静音消除
        self.enable_silence_check: bool = False     # 是否启用静音检测
        self.silence_retention_ratio: float = 0.5   # 保留的静音比例，范围 0-0.5，0.5 表示保留 50% 的静音片段。
        self.silence_threshold: int = -50           # 静音检测阈值（分贝），绝对值越大保留的声音越多。
        self.silent_duration: int = 500             # 静音持续时间（毫秒），超过此时间触发静音处理。建议不低于 300ms，过小可能导致音频频繁中断。

        # 背景音乐
        self.include_background_music: bool = True          # 是否添加背景音乐
        self.background_music_file: str = 'assets/bgm.mp3'  # 背景音乐文件路径
        self.background_music_volume: float = 0.1           # 背景音乐音量，范围0-1。

        # 视频镜像与旋转
        self.flip_horizontal: bool = False                   # 是否启用水平镜像 (enable_random_flip=False时生效)
        self.rotation_angle: int = -3                       # 旋转角度（度），建议值 -3 到 3。

        # 视频裁剪
        self.crop_percentage: float = 0.1                   # 裁剪百分比，范围 0-0.5，例如 0.1 表示裁剪每边 10% 的区域。

        # 淡入淡出
        self.fade_in_frames: int = 5                        # 淡入效果持续的帧数，建议 10-30 帧。
        self.fade_out_frames: int = 20                      # 淡出效果持续的帧数，建议 10-30 帧。

        # 画中画
        self.include_hzh: bool = True        # 是否启用画中画
        self.hzh_opacity: float = 0.1        # 画中画透明度
        self.hzh_scale: float = 1.0          # 画中画大小因子
        self.hzh_video_file: str = 'assets/hzh.mp4'  # 画中画视频文件路径

        # 颜色调整
        self.enable_sbc: bool = True         # 是否启用饱和度、亮度、对比度调整
        self.saturation: float = 1.05        # 饱和度调整因子，建议 0.8-1.2。值越小颜色越淡，值越大颜色越鲜艳。
        self.brightness: float = 0.05        # 亮度调整因子，建议 -0.3 到 0.3。负值降低亮度，正值增加亮度。
        self.contrast: float = 1.05          # 对比度调整因子，建议 0.8-1.2。值越小对比度越低，值越大对比度越高。

        # 背景模糊
        self.blur_background_enabled: bool = True           # 是否启用背景模糊
        self.top_blur_percentage: int = 3                   # 顶部模糊区域百分比，范围 0-100。
        self.bottom_blur_percentage: int = 3                # 底部模糊区域百分比，范围 0-100。
        self.side_blur_percentage: int = 3                  # 侧边模糊区域百分比，范围 0-100。

        # 高斯模糊
        self.gaussian_blur_interval: int = 15               # 高斯模糊帧步长，0 表示禁用。
        self.gaussian_blur_kernel_size: int = 3             # 高斯模糊核大小，必须为正奇数（如 1, 3, 5）。
        self.gaussian_blur_area_percentage: int = 15        # 高斯模糊区域大小百分比，范围 0-100。

        # 帧交换
        self.enable_frame_swap: bool = True                 # 是否启用帧交换
        self.frame_swap_interval: int = 15                  # 帧交换步长。建议值 5-20，每隔指定步长交换帧，增加动态效果。

        # 颜色偏移
        self.enable_color_shift: bool = True                # 是否启用颜色偏移
        self.color_shift_range: int = 3                     # 颜色偏移区间，3代表[-3,3]，该值越大颜色差距越明显

        # 高级效果
        self.scramble_frequency: float = 0.0                # 频域扰乱参数，0.0表示禁用，范围0.0-1.0，开启后处理时间较长。
        self.enable_texture_noise: bool = True              # 是否启用纹理噪声
        self.texture_noise_strength: float = 0.5            # 纹理噪声强度，范围 0-1，默认 0.5
        self.enable_blur_edge: bool = True                  # 是否启用边缘模糊

        # 元数据清洗参数
        self.enable_metadata_clean: bool = True             # 是否清洗视频元数据
        self.randomize_creation_time: bool = True           # 是否随机化创建时间
        
        # 音频指纹扰乱参数
        self.enable_audio_fingerprint_disrupt: bool = True  # 是否启用音频指纹扰乱
        self.pitch_shift_semitones: float = 0.3             # 音高偏移半音数，建议 0.1-0.5
        self.add_subliminal_noise: bool = True              # 是否添加极低音量噪声
        self.subliminal_noise_volume: float = 0.01          # 极低噪声音量，范围 0-0.05
        self.add_random_silence: bool = True                # 是否添加随机极短静音
        self.random_silence_duration_ms: int = 20           # 随机静音时长（毫秒），建议 10-50
        
        # 感知哈希扰乱参数
        self.enable_hash_disruption: bool = True            # 是否启用感知哈希扰乱
        self.hash_disruption_pixels: int = 2                # 边缘随机像素线宽度，建议 1-3
        self.hash_disruption_blocks: int = 5                # 随机色块数量，建议 3-10
        self.hash_disruption_block_size: int = 3            # 随机色块大小（像素），建议 2-5
        
        # 贴纸叠加参数
        self.enable_sticker: bool = True                   # 是否启用贴纸叠加
        self.sticker_folder: str = 'assets/stickers/'       # 贴纸文件夹路径
        self.sticker_opacity: float = 0.7                   # 贴纸透明度，范围 0-1
        self.sticker_scale_range: tuple = (0.08, 0.15)      # 贴纸大小范围（占画面比例）
        self.sticker_change_interval: int = 60              # 贴纸切换间隔（帧），0表示不切换
        self.sticker_position: str = 'corner'               # 贴纸位置：corner（四角随机）、random（完全随机）
        
        # 动态边框参数
        self.enable_dynamic_border: bool = True             # 是否启用动态边框
        self.border_width: int = 3                          # 边框宽度（像素），建议 2-8
        self.border_style: str = 'gradient'                 # 边框样式：solid（纯色）、gradient（渐变）、rainbow（彩虹）
        self.border_color_start: str = '#FF6B6B'            # 渐变起始颜色
        self.border_color_end: str = '#4ECDC4'              # 渐变结束颜色
        
        # 暗角效果参数
        self.enable_vignette: bool = True                   # 是否启用暗角效果
        self.vignette_strength: float = 0.3                 # 暗角强度，范围 0-1
        self.vignette_radius: float = 0.8                   # 暗角半径，范围 0.5-1.5
        
        # 时间轴随机化参数
        self.enable_timeline_randomize: bool = True         # 是否启用时间轴随机化
        self.add_intro_frames: int = 3                      # 添加片头帧数量，建议 1-5
        self.add_outro_frames: int = 3                      # 添加片尾帧数量，建议 1-5
        self.intro_outro_color: str = 'black'               # 片头片尾颜色：black、white、blur（模糊首尾帧）
        self.frame_drop_ratio: float = 0.003                # 随机丢帧比例，建议 0.001-0.01
        self.frame_duplicate_ratio: float = 0.002           # 随机复制帧比例，建议 0.001-0.005
        
        # DCT域扰动参数
        self.enable_dct_perturbation: bool = True           # 是否启用DCT域扰动
        self.dct_noise_strength: float = 0.02               # DCT噪声强度，范围 0.01-0.1

    def validate(self):
        """
        验证配置参数的有效性，确保所有参数和文件路径合法。
        """
        # GPU 加速
        if not isinstance(self.enable_gpu, bool):
            raise ValueError("enable_gpu 必须是布尔值")

        # 字幕参数
        if not isinstance(self.include_subtitles, bool):
            raise ValueError("include_subtitles 必须是布尔值")
        if not 0 <= self.subtitles_opacity <= 1:
            raise ValueError("subtitles_opacity 必须在 0 到 1 之间")
        if not isinstance(self.use_whisper, bool):
            raise ValueError("use_whisper 必须是布尔值")
        if not isinstance(self.whisper_model_name, str):
            raise ValueError("whisper_model_name 必须是字符串")
        if not isinstance(self.subtitles_file, str):
            raise ValueError("subtitles_file 必须是字符串")
        if not isinstance(self.subtitles_duration, (int, float)) or self.subtitles_duration < 0:
            raise ValueError("subtitles_duration 必须是非负数")
        if not self.is_valid_color(self.subtitles_color):
            raise ValueError("subtitles_color 必须是有效的颜色")

        # 标题参数
        if not isinstance(self.include_titles, bool):
            raise ValueError("include_titles 必须是布尔值")
        if not 0 <= self.titles_opacity <= 1:
            raise ValueError("titles_opacity 必须在 0 到 1 之间")
        if not isinstance(self.top_title, str):
            raise ValueError("top_title 必须是字符串")
        if not 0 <= self.top_title_margin <= 100:
            raise ValueError("top_title_margin 必须在 0 到 100 之间")
        if not isinstance(self.bottom_title, str):
            raise ValueError("bottom_title 必须是字符串")
        if not 0 <= self.bottom_title_margin <= 100:
            raise ValueError("bottom_title_margin 必须在 0 到 100 之间")
        if not self.is_valid_color(self.titles_color):
            raise ValueError("titles_color 必须是有效的颜色")

        # 水印参数
        if not isinstance(self.include_watermark, bool):
            raise ValueError("include_watermark 必须是布尔值")
        if not 0 <= self.watermark_opacity <= 1:
            raise ValueError("watermark_opacity 必须在 0 到 1 之间")
        if self.watermark_type not in ['text', 'image', 'video']:
            raise ValueError("watermark_type 必须是 'text', 'image' 或 'video'")
        if not self.is_valid_color(self.watermark_color):
            raise ValueError("watermark_color 必须是有效的颜色")
        if self.watermark_type == 'image' and not os.path.exists(self.watermark_image_path):
            raise FileNotFoundError(f"图片水印文件 {self.watermark_image_path} 不存在")
        if self.watermark_type == 'video' and not os.path.exists(self.watermark_video_path):
            raise FileNotFoundError(f"视频水印文件 {self.watermark_video_path} 不存在")

        # 字体
        if not isinstance(self.custom_font_enabled, bool):
            raise ValueError("custom_font_enabled 必须是布尔值")
        if self.custom_font_enabled and not os.path.exists(self.font_file):
            raise FileNotFoundError(f"字体文件 {self.font_file} 不存在")

        # 文字外边框
        if not isinstance(self.text_border_size, int) or self.text_border_size < 0:
            raise ValueError("text_border_size 必须是非负整数")

        # 音频参数
        if not isinstance(self.enable_silence_check, bool):
            raise ValueError("enable_silence_check 必须是布尔值")
        if not isinstance(self.silence_threshold, (int, float)):
            raise ValueError("silence_threshold 必须是数字")
        if not 0 <= self.silence_retention_ratio <= 1:
            raise ValueError("silence_retention_ratio 必须在 0 到 1 之间")
        if not isinstance(self.silent_duration, int) or self.silent_duration < 0:
            raise ValueError("silent_duration 必须是非负整数")

        # 背景音乐
        if not isinstance(self.include_background_music, bool):
            raise ValueError("include_background_music 必须是布尔值")
        if self.include_background_music and not os.path.exists(self.background_music_file):
            raise FileNotFoundError(f"背景音乐文件 {self.background_music_file} 不存在")
        if not 0 <= self.background_music_volume <= 1:
            raise ValueError("background_music_volume 必须在 0 到 1 之间")

        # 视频镜像与旋转
        if not isinstance(self.flip_horizontal, bool):
            raise ValueError("flip_horizontal 必须是布尔值")
        if not isinstance(self.enable_random_flip, bool):
            raise ValueError("enable_random_flip 必须是布尔值")
        if not isinstance(self.enable_speed_change, bool):
            raise ValueError("enable_speed_change 必须是布尔值")
        if not isinstance(self.speed_change_range, tuple) or len(self.speed_change_range) != 2:
            raise ValueError("speed_change_range 必须是包含两个浮点数的元组")
        if not isinstance(self.rotation_angle, (int, float)):
            raise ValueError("rotation_angle 必须是数字")

        # 视频裁剪
        if not 0 <= self.crop_percentage <= 0.5:
            raise ValueError("crop_percentage 必须在 0 到 0.5 之间")

        # 淡入淡出
        if not isinstance(self.fade_in_frames, int) or self.fade_in_frames < 0:
            raise ValueError("fade_in_frames 必须是非负整数")
        if not isinstance(self.fade_out_frames, int) or self.fade_out_frames < 0:
            raise ValueError("fade_out_frames 必须是非负整数")

        # 画中画
        if not isinstance(self.include_hzh, bool):
            raise ValueError("include_hzh 必须是布尔值")
        if not 0 <= self.hzh_opacity <= 1:
            raise ValueError("hzh_opacity 必须在 0 到 1 之间")
        if not 0 < self.hzh_scale <= 1:
            raise ValueError("hzh_scale 必须在 0 到 1 之间")
        if self.include_hzh and not os.path.exists(self.hzh_video_file):
            raise FileNotFoundError(f"画中画视频文件 {self.hzh_video_file} 不存在")

        # 颜色调整
        if not isinstance(self.enable_sbc, bool):
            raise ValueError("enable_sbc 必须是布尔值")
        if self.saturation < 0:
            raise ValueError("saturation 必须是非负数")
        if self.brightness < -1 or self.brightness > 1:
            raise ValueError("brightness 必须在 -1 到 1 之间")
        if self.contrast < 0:
            raise ValueError("contrast 必须是非负数")

        # 背景模糊
        if not isinstance(self.blur_background_enabled, bool):
            raise ValueError("blur_background_enabled 必须是布尔值")
        if not 0 <= self.top_blur_percentage <= 100:
            raise ValueError("top_blur_percentage 必须在 0 到 100 之间")
        if not 0 <= self.bottom_blur_percentage <= 100:
            raise ValueError("bottom_blur_percentage 必须在 0 到 100 之间")
        if not 0 <= self.side_blur_percentage <= 100:
            raise ValueError("side_blur_percentage 必须在 0 到 100 之间")

        # 高斯模糊
        if not isinstance(self.gaussian_blur_interval, int) or self.gaussian_blur_interval < 0:
            raise ValueError("gaussian_blur_interval 必须是非负整数")
        if self.gaussian_blur_kernel_size < 1 or self.gaussian_blur_kernel_size % 2 == 0:
            raise ValueError("gaussian_blur_kernel_size 必须是正奇数")
        if not 0 <= self.gaussian_blur_area_percentage <= 100:
            raise ValueError("gaussian_blur_area_percentage 必须在 0 到 100 之间")

        # 帧交换
        if not isinstance(self.enable_frame_swap, bool):
            raise ValueError("enable_frame_swap 必须是布尔值")
        if not isinstance(self.frame_swap_interval, int) or self.frame_swap_interval < 1:
            raise ValueError("frame_swap_interval 必须是正整数")

        # 颜色偏移
        if not isinstance(self.enable_color_shift, bool):
            raise ValueError("enable_color_shift 必须是布尔值")
        if not isinstance(self.color_shift_range, int) or self.color_shift_range < 0:
            raise ValueError("color_shift_range 必须是非负整数")

        # 高级效果
        if not 0 <= self.scramble_frequency <= 1:
            raise ValueError("scramble_frequency 必须在 0 到 1 之间")
        if not isinstance(self.enable_texture_noise, bool):
            raise ValueError("enable_texture_noise 必须是布尔值")
        if not 0 <= self.texture_noise_strength <= 1:
            raise ValueError("texture_noise_strength 必须在 0 到 1 之间")
        if not isinstance(self.enable_blur_edge, bool):
            raise ValueError("enable_blur_edge 必须是布尔值")

        # ========== 2025年新增参数验证 ==========
        
        # 元数据清洗
        if not isinstance(self.enable_metadata_clean, bool):
            raise ValueError("enable_metadata_clean 必须是布尔值")
        if not isinstance(self.randomize_creation_time, bool):
            raise ValueError("randomize_creation_time 必须是布尔值")
        
        # 音频指纹扰乱
        if not isinstance(self.enable_audio_fingerprint_disrupt, bool):
            raise ValueError("enable_audio_fingerprint_disrupt 必须是布尔值")
        if not 0 <= self.pitch_shift_semitones <= 2:
            raise ValueError("pitch_shift_semitones 必须在 0 到 2 之间")
        if not isinstance(self.add_subliminal_noise, bool):
            raise ValueError("add_subliminal_noise 必须是布尔值")
        if not 0 <= self.subliminal_noise_volume <= 0.1:
            raise ValueError("subliminal_noise_volume 必须在 0 到 0.1 之间")
        
        # 感知哈希扰乱
        if not isinstance(self.enable_hash_disruption, bool):
            raise ValueError("enable_hash_disruption 必须是布尔值")
        if not 1 <= self.hash_disruption_pixels <= 5:
            raise ValueError("hash_disruption_pixels 必须在 1 到 5 之间")
        if not 0 <= self.hash_disruption_blocks <= 20:
            raise ValueError("hash_disruption_blocks 必须在 0 到 20 之间")
        
        # 贴纸叠加
        if not isinstance(self.enable_sticker, bool):
            raise ValueError("enable_sticker 必须是布尔值")
        if not 0 <= self.sticker_opacity <= 1:
            raise ValueError("sticker_opacity 必须在 0 到 1 之间")
        if self.sticker_position not in ['corner', 'random']:
            raise ValueError("sticker_position 必须是 'corner' 或 'random'")
        
        # 动态边框
        if not isinstance(self.enable_dynamic_border, bool):
            raise ValueError("enable_dynamic_border 必须是布尔值")
        if not 0 <= self.border_width <= 20:
            raise ValueError("border_width 必须在 0 到 20 之间")
        if self.border_style not in ['solid', 'gradient', 'rainbow']:
            raise ValueError("border_style 必须是 'solid', 'gradient' 或 'rainbow'")
        
        # 暗角效果
        if not isinstance(self.enable_vignette, bool):
            raise ValueError("enable_vignette 必须是布尔值")
        if not 0 <= self.vignette_strength <= 1:
            raise ValueError("vignette_strength 必须在 0 到 1 之间")
        if not 0.3 <= self.vignette_radius <= 2:
            raise ValueError("vignette_radius 必须在 0.3 到 2 之间")
        
        # 时间轴随机化
        if not isinstance(self.enable_timeline_randomize, bool):
            raise ValueError("enable_timeline_randomize 必须是布尔值")
        if not 0 <= self.add_intro_frames <= 30:
            raise ValueError("add_intro_frames 必须在 0 到 30 之间")
        if not 0 <= self.add_outro_frames <= 30:
            raise ValueError("add_outro_frames 必须在 0 到 30 之间")
        if not 0 <= self.frame_drop_ratio <= 0.05:
            raise ValueError("frame_drop_ratio 必须在 0 到 0.05 之间")
        if not 0 <= self.frame_duplicate_ratio <= 0.05:
            raise ValueError("frame_duplicate_ratio 必须在 0 到 0.05 之间")
        
        # DCT域扰动
        if not isinstance(self.enable_dct_perturbation, bool):
            raise ValueError("enable_dct_perturbation 必须是布尔值")
        if not 0 <= self.dct_noise_strength <= 0.5:
            raise ValueError("dct_noise_strength 必须在 0 到 0.5 之间")

        # 验证文件路径
        paths_to_check = [
            (self.background_music_file, "背景音乐文件"),
            (self.subtitles_file, "字幕文件"),
            (self.font_file, "字体文件"),
            (self.hzh_video_file if self.include_hzh else "", "画中画视频文件"),
            (self.watermark_image_path if self.watermark_type == 'image' else "", "图片水印文件"),
            (self.watermark_video_path if self.watermark_type == 'video' else "", "视频水印文件")
        ]
        for path, desc in paths_to_check:
            if path and not os.path.exists(path):
                raise FileNotFoundError(f"{desc} {path} 不存在")

    @staticmethod
    def is_valid_color(color_str: str) -> bool:
        """
        检查颜色字符串是否有效（支持颜色名称或 HEX 码）。

        参数:
            color_str: 颜色字符串，例如 'yellow' 或 '#FFFF00'

        返回:
            bool: True 表示颜色有效，False 表示无效
        """
        if color_str.startswith('#'):
            return bool(re.match(r'^#[0-9A-Fa-f]{6}$', color_str))
        valid_colors = ['yellow', 'red', 'green', 'blue', 'white', 'black']
        return color_str.lower() in valid_colors

class FFmpegHandler:
    """
    FFmpeg 工具类，用于处理音视频流。
    """
    @staticmethod
    def split_av_streams(input_path: str) -> Tuple[ffmpeg.Stream, ffmpeg.Stream]:
        """
        分离输入视频的音频流和视频流。

        参数:
            input_path: 输入视频文件路径

        返回:
            Tuple[ffmpeg.Stream, ffmpeg.Stream]: 视频流和音频流（如果存在）
        """
        try:
            probe = ffmpeg.probe(input_path)
            video_stream = next((s for s in probe['streams'] if s['codec_type'] == 'video'), None)
            audio_stream = next((s for s in probe['streams'] if s['codec_type'] == 'audio'), None)
            if not video_stream:
                raise ValueError("未找到视频流")
            stream = ffmpeg.input(input_path)
            return stream.video, stream.audio if audio_stream else None
        except ffmpeg.Error as e:
            logging.error(f"分离音视频流失败: {e.stderr.decode()}")
            raise

    @staticmethod
    def get_video_properties(input_path: str) -> Tuple[int, int, float]:
        """
        获取视频的宽度、高度和帧率。

        参数:
            input_path: 输入视频文件路径

        返回:
            Tuple[int, int, float]: 宽度、高度和帧率
        """
        try:
            probe = ffmpeg.probe(input_path)
            video_info = next(s for s in probe['streams'] if s['codec_type'] == 'video')
            return (int(video_info['width']), int(video_info['height']),
                    float(eval(video_info['r_frame_rate'])))
        except ffmpeg.Error as e:
            logging.error(f"获取视频属性失败: {e.stderr.decode()}")
            raise

class AudioHandler:
    """
    音频处理类，用于静音去除和背景音乐混合。
    """
    @staticmethod
    def remove_silence(audio_path: str, config: VideoConfig) -> str:
        """
        删除音频中的静音部分，保留所有非静音内容。

        参数:
            audio_path: 输入音频文件路径
            config: 视频处理配置对象

        返回:
            str: 处理后的音频文件路径
        """
        if not config.enable_silence_check:
            return audio_path

        try:
            audio = AudioSegment.from_file(audio_path)
            chunks = split_on_silence(audio, min_silence_len=config.silent_duration,
                                      silence_thresh=config.silence_threshold)
            if not chunks:
                logging.warning("未检测到非静音片段，返回原始音频")
                return audio_path
            processed_audio = AudioSegment.silent(duration=0)  # 初始化空音频
            for chunk in chunks:
                processed_audio += chunk  # 直接拼接所有非静音片段
                if config.silence_retention_ratio > 0:  # 可选：在片段间添加少量静音
                    silence_duration = int(config.silent_duration * config.silence_retention_ratio)
                    processed_audio += AudioSegment.silent(duration=silence_duration)
            output_path = tempfile.mktemp(suffix='.wav')
            processed_audio.export(output_path, format='wav')
            logging.info(f"静音处理完成，输出到 {output_path}")
            return output_path
        except Exception as e:
            logging.error(f"静音处理失败: {str(e)}")
            raise

    @staticmethod
    def mix_bgm(original_audio_path: str, bgm_path: str, background_music_volume: float = 0.5) -> str:
        """
        将原始音频与背景音乐混合，支持音量调节。
        参数:
            original_audio_path: 原始音频文件路径
            bgm_path: 背景音乐文件路径
            background_music_volume: 背景音乐音量，范围0-1
        返回:
            str: 混合后的音频文件路径
        """
        if not bgm_path or not os.path.exists(bgm_path):
            logging.warning("背景音乐路径无效，返回原始音频")
            return original_audio_path
        try:
            original = AudioSegment.from_file(original_audio_path)
            bgm = AudioSegment.from_file(bgm_path)
            # 调整BGM音量：转换为分贝调整，0时静音，1时保持原音量
            bgm = bgm + 20 * math.log10(background_music_volume) if background_music_volume > 0 else bgm - 60  # -60dB接近静音
            mixed = original.overlay(bgm, loop=True)
            mixed_path = tempfile.mktemp(suffix='.wav')
            mixed.export(mixed_path, format='wav')
            logging.info(f"背景音乐混合完成，输出到 {mixed_path}")
            return mixed_path
        except Exception as e:
            logging.error(f"背景音乐混合失败: {str(e)}")
            raise

class MetadataHandler:
    """
    元数据处理类，用于清洗视频元数据以增强去重效果。
    通过去除原始元数据、随机化创建时间等方式干扰平台的视频识别。
    """
    
    @staticmethod
    def clean_metadata(video_path: str, config: VideoConfig) -> None:
        """
        清洗视频元数据。
        
        参数:
            video_path: 视频文件路径
            config: 视频处理配置对象
        """
        if not config.enable_metadata_clean:
            return
        
        try:
            import subprocess
            import datetime
            
            # 创建临时文件路径
            temp_path = video_path + '.tmp.mp4'
            
            # 构建 FFmpeg 命令
            cmd = ['ffmpeg', '-y', '-i', video_path, '-map_metadata', '-1']
            
            # 随机化创建时间
            if config.randomize_creation_time:
                # 生成随机的创建时间（过去30天内的随机时间）
                days_ago = random.randint(1, 30)
                hours_offset = random.randint(0, 23)
                minutes_offset = random.randint(0, 59)
                random_time = datetime.datetime.now() - datetime.timedelta(
                    days=days_ago, hours=hours_offset, minutes=minutes_offset
                )
                creation_time = random_time.strftime('%Y-%m-%dT%H:%M:%S')
                cmd.extend(['-metadata', f'creation_time={creation_time}'])
                logging.info(f"随机化创建时间: {creation_time}")
            
            # 添加随机编码器标识
            encoders = ['Lavf58.76.100', 'Lavf59.27.100', 'Lavf60.3.100', 'HandBrake', 'FFmpeg']
            random_encoder = random.choice(encoders)
            cmd.extend(['-metadata', f'encoder={random_encoder}'])
            
            # 复制视频和音频流，不重新编码
            cmd.extend(['-c', 'copy', temp_path])
            
            # 执行命令
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                # 替换原文件
                import shutil
                shutil.move(temp_path, video_path)
                logging.info(f"元数据清洗完成: {video_path}")
            else:
                logging.warning(f"元数据清洗失败: {result.stderr}")
                # 清理临时文件
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    
        except Exception as e:
            logging.error(f"元数据清洗异常: {str(e)}")
            # 确保清理临时文件
            temp_path = video_path + '.tmp.mp4'
            if os.path.exists(temp_path):
                os.remove(temp_path)

class AudioFingerprintDisruptor:
    """
    音频指纹扰乱类，用于干扰平台的音频指纹检测算法（如 Acoustid/Chromaprint）。
    通过音高偏移、添加极低音量噪声、随机静音插入等方式实现。
    """
    
    @staticmethod
    def disrupt_audio(audio_path: str, config: VideoConfig) -> str:
        """
        对音频进行指纹扰乱处理。
        
        参数:
            audio_path: 输入音频文件路径
            config: 视频处理配置对象
            
        返回:
            str: 处理后的音频文件路径
        """
        if not config.enable_audio_fingerprint_disrupt:
            return audio_path
            
        try:
            audio = AudioSegment.from_file(audio_path)
            
            # 1. 音高偏移（通过改变采样率实现）
            if config.pitch_shift_semitones > 0:
                # 计算变调因子：每个半音是 2^(1/12) ≈ 1.0595
                shift_direction = random.choice([1, -1])
                semitones = config.pitch_shift_semitones * shift_direction
                pitch_factor = 2 ** (semitones / 12.0)
                
                # 改变采样率来实现变调
                new_sample_rate = int(audio.frame_rate * pitch_factor)
                audio = audio._spawn(audio.raw_data, overrides={
                    'frame_rate': new_sample_rate
                })
                # 恢复原采样率（改变播放速度恢复正常）
                audio = audio.set_frame_rate(44100)
                logging.info(f"音频音高偏移: {semitones:.2f} 半音")
            
            # 2. 添加极低音量噪声
            if config.add_subliminal_noise:
                duration_ms = len(audio)
                # 生成白噪声
                noise_samples = np.random.normal(0, 1, int(audio.frame_rate * duration_ms / 1000))
                # 转换为 int16
                noise_samples = (noise_samples * 32767 * config.subliminal_noise_volume).astype(np.int16)
                # 创建噪声音频段
                noise_audio = AudioSegment(
                    noise_samples.tobytes(),
                    frame_rate=audio.frame_rate,
                    sample_width=2,
                    channels=1
                )
                # 如果原音频是立体声，转换噪声为立体声
                if audio.channels == 2:
                    noise_audio = AudioSegment.from_mono_audiosegments(noise_audio, noise_audio)
                # 调整噪声长度
                noise_audio = noise_audio[:len(audio)]
                # 叠加噪声
                audio = audio.overlay(noise_audio)
                logging.info(f"已添加极低音量噪声，音量: {config.subliminal_noise_volume}")
            
            # 3. 随机插入极短静音
            if config.add_random_silence:
                # 每隔一段时间插入一个极短静音
                silence = AudioSegment.silent(duration=config.random_silence_duration_ms)
                output_audio = AudioSegment.silent(duration=0)
                chunk_size = random.randint(5000, 15000)  # 5-15秒随机
                
                pos = 0
                insert_count = 0
                while pos < len(audio):
                    end_pos = min(pos + chunk_size, len(audio))
                    output_audio += audio[pos:end_pos]
                    if end_pos < len(audio):
                        output_audio += silence
                        insert_count += 1
                    pos = end_pos
                    chunk_size = random.randint(5000, 15000)
                
                audio = output_audio
                logging.info(f"已插入 {insert_count} 个随机静音段，每段 {config.random_silence_duration_ms}ms")
            
            # 导出处理后的音频
            output_path = tempfile.mktemp(suffix='.wav')
            audio.export(output_path, format='wav')
            logging.info(f"音频指纹扰乱完成，输出到 {output_path}")
            return output_path
            
        except Exception as e:
            logging.error(f"音频指纹扰乱失败: {str(e)}")
            return audio_path

class SubtitleHandler:
    """字幕处理类，用于生成和添加字幕"""
    
    @staticmethod
    def generate_subtitles(input_path: str, model_name: str = 'base') -> str:
        """使用 Whisper 生成字幕文件，并将繁体中文转换为简体中文"""
        try:
            import warnings
            # 抑制 FP16 警告
            warnings.filterwarnings("ignore", message="FP16 is not supported on CPU; using FP32 instead")
            model = whisper.load_model(model_name)
            result = model.transcribe(input_path)
            srt_path = tempfile.NamedTemporaryFile(suffix='.srt', delete=False).name
            converter = opencc.OpenCC('t2s')  # 繁体转简体
            with open(srt_path, 'w', encoding='utf-8') as f:
                for i, segment in enumerate(result['segments']):
                    start = segment['start']
                    end = segment['end']
                    text = converter.convert(segment['text'].strip())  # 转换为简体中文
                    f.write(f"{i+1}\n")
                    f.write(f"{SubtitleHandler.format_time(start)} --> {SubtitleHandler.format_time(end)}\n")
                    f.write(f"{text}\n\n")
            logging.debug(f"字幕文件生成: {srt_path}")
            return srt_path
        except Exception as e:
            logging.error(f"字幕生成失败: {str(e)}")
            raise

    @staticmethod
    def format_time(seconds: float) -> str:
        """将秒数格式化为 SRT 时间格式"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}".replace('.', ',')

class VideoEffects:
    """
    视频特效类，包含水印、字幕、模糊等效果的实现。
    """
    @staticmethod
    def add_watermark(frame: np.ndarray, config: VideoConfig, frame_idx: int, total_frames: int, handler: 'VideoHandler' = None) -> np.ndarray:
        """
        在视频帧上添加水印（支持文本、图片和视频水印）。

        参数:
            frame: 当前视频帧
            config: 视频处理配置对象
            frame_idx: 当前帧索引
            total_frames: 视频总帧数

        返回:
            np.ndarray: 添加水印后的帧
        """
        h, w = frame.shape[:2]
        
        if config.watermark_type == 'text' and config.watermark_text:
            # 保持原有文本水印逻辑不变
            font_size = max(10, min(h // 20, w // len(config.watermark_text)))
            font = ImageFont.truetype(config.font_file, font_size) if config.custom_font_enabled and os.path.exists(config.font_file) else ImageFont.load_default()
            pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(pil_img)
            text_bbox = draw.textbbox((0, 0), config.watermark_text, font=font)
            text_width, text_height = text_bbox[2] - text_bbox[0], text_bbox[3] - text_bbox[1]
            x, y = VideoEffects.get_watermark_position(config.watermark_direction, frame_idx, total_frames, w, h, text_width, text_height)
            x, y = max(0, min(x, w - text_width)), max(0, min(y, h - text_height))
            color = VideoEffects.parse_color(config.watermark_color)
            border_size = config.text_border_size
            opacity = config.watermark_opacity
            
            if opacity < 1.0:
                watermark_img = Image.new('RGBA', pil_img.size, (0, 0, 0, 0))
                watermark_draw = ImageDraw.Draw(watermark_img)
                border_color = (0, 0, 0, int(255 * opacity))
                for dx in range(-border_size, border_size + 1):
                    for dy in range(-border_size, border_size + 1):
                        if dx != 0 or dy != 0:
                            watermark_draw.text((x + dx, y + dy), config.watermark_text, font=font, fill=border_color)
                text_color = (*color, int(255 * opacity))
                watermark_draw.text((x, y), config.watermark_text, font=font, fill=text_color)
                pil_img = Image.alpha_composite(pil_img.convert('RGBA'), watermark_img).convert('RGB')
            else:
                for dx in range(-border_size, border_size + 1):
                    for dy in range(-border_size, border_size + 1):
                        if dx != 0 or dy != 0:
                            draw.text((x + dx, y + dy), config.watermark_text, font=font, fill=(0, 0, 0))
                draw.text((x, y), config.watermark_text, font=font, fill=color)
            return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        
        elif config.watermark_type == 'image' and config.watermark_image_path and handler and handler.wm_rgb is not None:
            wm_width, wm_height = handler.watermark_img.size
            x, y = VideoEffects.get_watermark_position(config.watermark_direction, frame_idx, total_frames, w, h, wm_width, wm_height)
            if x + wm_width > w or y + wm_height > h or x < 0 or y < 0:
                return frame
            roi = frame[y:y+wm_height, x:x+wm_width]
            for c in range(3):
                roi[:, :, c] = (1 - handler.wm_alpha) * roi[:, :, c] + handler.wm_alpha * handler.wm_rgb[:, :, c]
            frame[y:y+wm_height, x:x+wm_width] = roi
        
        elif config.watermark_type == 'video' and config.watermark_video_path:
            # 视频水印（未来扩展）
            # 这里仅提供占位逻辑，实际实现需要同步视频帧
            # 由于需要同步视频帧，复杂度较高，此处仅记录为待实现功能，可在未来通过在 VideoHandler 中加载水印视频帧并传递到此方法实现。
            logging.warning("视频水印功能尚未实现")
            pass
        
        return frame

    @staticmethod
    def parse_color(color_str: str) -> Tuple[int, int, int]:
        """将颜色字符串解析为 BGR 元组"""
        if color_str.startswith('#'):  # 支持 HEX 码
            r, g, b = tuple(int(color_str[i:i+2], 16) for i in (1, 3, 5))
            return (b, g, r)  # 返回 BGR
        colors = {
            'yellow': (0, 255, 255),  # BGR
            'red': (0, 0, 255),
            'green': (0, 255, 0),
            'blue': (255, 0, 0),
            'white': (255, 255, 255),
            'black': (0, 0, 0),
            'cyan': (255, 255, 0),
            'magenta': (255, 0, 255),
            'orange': (0, 165, 255),
            'purple': (128, 0, 128),
            'brown': (42, 42, 165),
            'gray': (128, 128, 128)
        }
        return colors.get(color_str.lower(), (255, 255, 255))  # 默认白色

    @staticmethod
    def get_watermark_position(direction: str, frame_index: int, total_frames: int,
                               video_width: int, video_height: int, watermark_width: int,
                               watermark_height: int) -> Tuple[int, int]:
        """
        计算动态水印的坐标位置，支持米字形8方向运动。

        参数:
            direction: 运动方向，支持以下模式：
                - 'left_to_right': 从左侧到右侧水平移动
                - 'right_to_left': 从右侧到左侧水平移动
                - 'top_to_bottom': 从顶部到底部垂直移动
                - 'bottom_to_top': 从底部到顶部垂直移动
                - 'lt_to_rb': 左上到右下对角线移动
                - 'rt_to_lb': 右上到左下对角线移动
                - 'lb_to_rt': 左下到右上对角线移动
                - 'rb_to_lt': 右下到左上对角线移动
            frame_index: 当前帧序号 (从0开始)
            total_frames: 视频总帧数
            video_width: 视频宽度 (像素)
            video_height: 视频高度 (像素)
            watermark_width: 水印宽度 (像素)
            watermark_height: 水印高度 (像素)

        返回:
            Tuple[int, int]: 水印的 x, y 坐标
        """
        MARGIN = 20  # 安全边距

        if direction == 'random':
            # 随机生成 x 和 y 坐标，确保在安全边距内
            x = random.randint(MARGIN, video_width - watermark_width - MARGIN)
            y = random.randint(MARGIN, video_height - watermark_height - MARGIN)
        else:
            progress = frame_index / total_frames
            
            # 计算可用移动范围
            range_x = video_width - watermark_width - 2 * MARGIN
            range_y = video_height - watermark_height - 2 * MARGIN
            
            if direction == 'left_to_right':
                x = MARGIN + int(range_x * progress)
                y = (video_height - watermark_height) // 2  # 垂直居中
            elif direction == 'right_to_left':
                x = video_width - MARGIN - watermark_width - int(range_x * progress)
                y = (video_height - watermark_height) // 2
            elif direction == 'top_to_bottom':
                x = (video_width - watermark_width) // 2    # 水平居中
                y = MARGIN + int(range_y * progress)
            elif direction == 'bottom_to_top':
                x = (video_width - watermark_width) // 2
                y = video_height - MARGIN - watermark_height - int(range_y * progress)
            elif direction == 'lt_to_rb':  # 左上→右下
                x = MARGIN + int(range_x * progress)
                y = MARGIN + int(range_y * progress)
            elif direction == 'rt_to_lb':  # 右上→左下
                x = video_width - MARGIN - watermark_width - int(range_x * progress)
                y = MARGIN + int(range_y * progress)
            elif direction == 'lb_to_rt':  # 左下→右上
                x = MARGIN + int(range_x * progress)
                y = video_height - MARGIN - watermark_height - int(range_y * progress)
            elif direction == 'rb_to_lt':  # 右下→左上
                x = video_width - MARGIN - watermark_width - int(range_x * progress)
                y = video_height - MARGIN - watermark_height - int(range_y * progress)
            else:  # 默认居中显示
                x = (video_width - watermark_width) // 2
                y = (video_height - watermark_height) // 2

        return (x, y)

    @staticmethod
    def add_subtitles(frame: np.ndarray, config: VideoConfig, frame_idx: int, 
                    fps: float, subs: pysrt.SubRipFile) -> np.ndarray:
        """
        在视频帧上添加字幕。

        参数:
            frame: 当前视频帧
            config: 视频处理配置对象
            frame_idx: 当前帧索引
            fps: 视频帧率
            subs: 字幕文件对象

        返回:
            np.ndarray: 添加字幕后的帧
        """
        if not config.subtitles_file or not os.path.exists(config.subtitles_file) or not subs:
            return frame
        current_time = frame_idx / fps
        def time_to_seconds(time_obj):
            return (time_obj.hours * 3600 + time_obj.minutes * 60 + 
                    time_obj.seconds + time_obj.milliseconds / 1000.0)
        for sub in subs:
            start_time = time_to_seconds(sub.start)
            end_time = time_to_seconds(sub.end)
            if start_time <= current_time <= end_time:
                pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                draw = ImageDraw.Draw(pil_img)
                font = ImageFont.truetype(config.font_file, 30) if config.custom_font_enabled and os.path.exists(config.font_file) else ImageFont.load_default()
                text_bbox = draw.textbbox((0, 0), sub.text, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
                x = (frame.shape[1] - text_width) // 2
                y = frame.shape[0] - text_height - 20
                color = VideoEffects.parse_color(config.subtitles_color)
                border_size = config.text_border_size
                opacity = config.subtitles_opacity
                if opacity < 1.0:
                    # 创建透明的字幕层
                    subtitle_img = Image.new('RGBA', pil_img.size, (0, 0, 0, 0))
                    subtitle_draw = ImageDraw.Draw(subtitle_img)
                    # 绘制外边框，透明度一致
                    border_color = (0, 0, 0, int(255 * opacity))
                    for dx in range(-border_size, border_size + 1):
                        for dy in range(-border_size, border_size + 1):
                            if dx != 0 or dy != 0:
                                subtitle_draw.text((x + dx, y + dy), sub.text, font=font, fill=border_color)
                    # 绘制文字，透明度一致
                    text_color = (*color, int(255 * opacity))
                    subtitle_draw.text((x, y), sub.text, font=font, fill=text_color)
                    # 合成图像
                    pil_img = Image.alpha_composite(pil_img.convert('RGBA'), subtitle_img).convert('RGB')
                else:
                    # 无透明度，直接绘制
                    for dx in range(-border_size, border_size + 1):
                        for dy in range(-border_size, border_size + 1):
                            if dx != 0 or dy != 0:
                                draw.text((x + dx, y + dy), sub.text, font=font, fill=(0, 0, 0))
                    draw.text((x, y), sub.text, font=font, fill=color)
                return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        return frame

    @staticmethod
    def add_titles(frame: np.ndarray, config: VideoConfig) -> np.ndarray:
        """
        在视频帧上添加顶部和底部标题。

        参数:
            frame: 当前视频帧
            config: 视频处理配置对象

        返回:
            np.ndarray: 添加标题后的帧
        """
        pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_img)
        font = ImageFont.truetype(config.font_file, 30) if config.custom_font_enabled and os.path.exists(config.font_file) else ImageFont.load_default()
        color = VideoEffects.parse_color(config.titles_color)
        border_size = config.text_border_size
        opacity = config.titles_opacity

        if config.top_title:
            text_bbox = draw.textbbox((0, 0), config.top_title, font=font)
            text_width, text_height = text_bbox[2] - text_bbox[0], text_bbox[3] - text_bbox[1]
            x = (frame.shape[1] - text_width) // 2
            y = int(frame.shape[0] * config.top_title_margin / 100)
            if opacity < 1.0:
                # 创建透明的标题层
                title_img = Image.new('RGBA', pil_img.size, (0, 0, 0, 0))
                title_draw = ImageDraw.Draw(title_img)
                # 绘制外边框，透明度一致
                border_color = (0, 0, 0, int(255 * opacity))
                for dx in range(-border_size, border_size + 1):
                    for dy in range(-border_size, border_size + 1):
                        if dx != 0 or dy != 0:
                            title_draw.text((x + dx, y + dy), config.top_title, font=font, fill=border_color)
                # 绘制文字，透明度一致
                text_color = (*color, int(255 * opacity))
                title_draw.text((x, y), config.top_title, font=font, fill=text_color)
                # 合成图像
                pil_img = Image.alpha_composite(pil_img.convert('RGBA'), title_img).convert('RGB')
            else:
                # 无透明度，直接绘制
                for dx in range(-border_size, border_size + 1):
                    for dy in range(-border_size, border_size + 1):
                        if dx != 0 or dy != 0:
                            draw.text((x + dx, y + dy), config.top_title, font=font, fill=(0, 0, 0))
                draw.text((x, y), config.top_title, font=font, fill=color)

        if config.bottom_title:
            text_bbox = draw.textbbox((0, 0), config.bottom_title, font=font)
            text_width, text_height = text_bbox[2] - text_bbox[0], text_bbox[3] - text_bbox[1]
            x = (frame.shape[1] - text_width) // 2
            y = frame.shape[0] - text_height - int(frame.shape[0] * config.bottom_title_margin / 100)
            if opacity < 1.0:
                # 创建透明的标题层
                title_img = Image.new('RGBA', pil_img.size, (0, 0, 0, 0))
                title_draw = ImageDraw.Draw(title_img)
                # 绘制外边框，透明度一致
                border_color = (0, 0, 0, int(255 * opacity))
                for dx in range(-border_size, border_size + 1):
                    for dy in range(-border_size, border_size + 1):
                        if dx != 0 or dy != 0:
                            title_draw.text((x + dx, y + dy), config.bottom_title, font=font, fill=border_color)
                # 绘制文字，透明度一致
                text_color = (*color, int(255 * opacity))
                title_draw.text((x, y), config.bottom_title, font=font, fill=text_color)
                # 合成图像
                pil_img = Image.alpha_composite(pil_img.convert('RGBA'), title_img).convert('RGB')
            else:
                # 无透明度，直接绘制
                for dx in range(-border_size, border_size + 1):
                    for dy in range(-border_size, border_size + 1):
                        if dx != 0 or dy != 0:
                            draw.text((x + dx, y + dy), config.bottom_title, font=font, fill=(0, 0, 0))
                draw.text((x, y), config.bottom_title, font=font, fill=color)

        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    @staticmethod
    def apply_gaussian_blur(frame: np.ndarray, config: VideoConfig, frame_idx: int) -> np.ndarray:
        """
        在指定帧上应用高斯模糊效果。

        参数:
            frame: 当前视频帧
            config: 视频处理配置对象
            frame_idx: 当前帧索引

        返回:
            np.ndarray: 应用高斯模糊后的帧
        """
        if config.gaussian_blur_interval == 0 or frame_idx % config.gaussian_blur_interval != 0:
            return frame
        kernel = config.gaussian_blur_kernel_size if config.gaussian_blur_kernel_size % 2 == 1 else config.gaussian_blur_kernel_size + 1
        area_size = config.gaussian_blur_area_percentage / 100
        h, w = frame.shape[:2]
        blur_h = int(h * area_size)
        blur_w = int(w * area_size)
        # 只模糊指定区域，避免重复处理整个帧
        frame[0:blur_h, :] = cv2.GaussianBlur(frame[0:blur_h, :], (kernel, kernel), 0)
        frame[h-blur_h:h, :] = cv2.GaussianBlur(frame[h-blur_h:h, :], (kernel, kernel), 0)
        frame[:, 0:blur_w] = cv2.GaussianBlur(frame[:, 0:blur_w], (kernel, kernel), 0)
        frame[:, w-blur_w:w] = cv2.GaussianBlur(frame[:, w-blur_w:w], (kernel, kernel), 0)
        return frame

    @staticmethod
    def rotate_frame(frame: np.ndarray, config: VideoConfig) -> np.ndarray:
        """
        旋转视频帧。

        参数:
            frame: 当前视频帧
            config: 视频处理配置对象

        返回:
            np.ndarray: 旋转后的帧
        """
        if config.rotation_angle != 0:
            h, w = frame.shape[:2]
            center = (w // 2, h // 2)
            matrix = cv2.getRotationMatrix2D(center, config.rotation_angle, 1.0)
            frame = cv2.warpAffine(frame, matrix, (w, h))
        return frame

    @staticmethod
    def adjust_sbc(frame: np.ndarray, config: VideoConfig) -> np.ndarray:
        """
        调整视频帧的饱和度、亮度和对比度。

        参数:
            frame: 当前视频帧
            config: 视频处理配置对象

        返回:
            np.ndarray: 调整后的帧
        """
        if config.enable_sbc:
            frame = cv2.convertScaleAbs(frame, alpha=config.contrast, beta=config.brightness * 255)
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            hsv[:, :, 1] = np.clip(hsv[:, :, 1] * config.saturation, 0, 255)
            frame = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        return frame

    @staticmethod
    def blur_background(frame: np.ndarray, config: VideoConfig) -> np.ndarray:
        """
        对视频帧的背景应用模糊效果。

        参数:
            frame: 当前视频帧
            config: 视频处理配置对象

        返回:
            np.ndarray: 应用背景模糊后的帧
        """
        if not config.blur_background_enabled:
            return frame
        h, w = frame.shape[:2]
        top = int(h * config.top_blur_percentage / 100)
        bottom = int(h * config.bottom_blur_percentage / 100)
        side = int(w * config.side_blur_percentage / 100)
        frame[:top, :] = cv2.GaussianBlur(frame[:top, :], (21, 21), 0)
        frame[-bottom:, :] = cv2.GaussianBlur(frame[-bottom:, :], (21, 21), 0)
        frame[:, :side] = cv2.GaussianBlur(frame[:, :side], (21, 21), 0)
        frame[:, -side:] = cv2.GaussianBlur(frame[:, -side:], (21, 21), 0)
        return frame

    @staticmethod
    def apply_fade_effect(frame: np.ndarray, config: VideoConfig, frame_idx: int, total_frames: int) -> np.ndarray:
        """
        在单帧级别应用淡入淡出效果。

        参数:
            frame: 当前视频帧
            config: 视频处理配置对象
            frame_idx: 当前帧索引
            total_frames: 视频总帧数

        返回:
            np.ndarray: 应用淡入淡出效果后的帧
        """
        if frame_idx < config.fade_in_frames:
            alpha = frame_idx / config.fade_in_frames
            frame = cv2.addWeighted(frame, alpha, np.zeros_like(frame), 1 - alpha, 0)
        elif frame_idx >= total_frames - config.fade_out_frames:
            alpha = (total_frames - frame_idx) / config.fade_out_frames
            frame = cv2.addWeighted(frame, alpha, np.zeros_like(frame), 1 - alpha, 0)
        return frame

    @staticmethod
    def color_shift(frame: np.ndarray, config: VideoConfig) -> np.ndarray:
        """
        对视频帧应用颜色偏移效果。

        参数:
            frame: 当前视频帧
            config: 视频处理配置对象

        返回:
            np.ndarray: 应用颜色偏移后的帧
        """
        if config.enable_color_shift:
            b, g, r = cv2.split(frame)
            shift = random.randint(-config.color_shift_range, config.color_shift_range)
            b = b.astype(np.int16)
            g = g.astype(np.int16)
            b = np.clip(b + shift, 0, 255).astype(np.uint8)
            g = np.clip(g - shift, 0, 255).astype(np.uint8)
            frame = cv2.merge((b, g, r))
        return frame

    @staticmethod
    def add_hzh_effect(frame: np.ndarray, config: VideoConfig, frame_idx: int, total_frames: int) -> np.ndarray:
        """
        在视频帧上添加画中画效果。

        参数:
            frame: 当前视频帧
            config: 视频处理配置对象
            frame_idx: 当前帧索引
            total_frames: 视频总帧数

        返回:
            np.ndarray: 添加画中画效果后的帧
        """
        if not config.include_hzh or not os.path.exists(config.hzh_video_file):
            return frame
        cap = cv2.VideoCapture(config.hzh_video_file)
        hzh_frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        hzh_idx = frame_idx % hzh_frame_count
        cap.set(cv2.CAP_PROP_POS_FRAMES, hzh_idx)
        ret, hzh_frame = cap.read()
        cap.release()
        if ret:
            h, w = frame.shape[:2]
            hzh_h, hzh_w = int(h * config.hzh_scale), int(w * config.hzh_scale)
            hzh_frame = cv2.resize(hzh_frame, (hzh_w, hzh_h))
            hzh_frame = cv2.cvtColor(hzh_frame, cv2.COLOR_BGR2RGB)  # 转换为 RGB
            # 计算居中位置
            x = (w - hzh_w) // 2
            y = (h - hzh_h) // 2
            # 检查画中画是否超出原视频尺寸
            if x < 0 or y < 0 or x + hzh_w > w or y + hzh_h > h:
                # 当尺寸超出时，直接覆盖整个画面
                frame = cv2.resize(hzh_frame, (w, h))
            else:
                # 正常情况下，使用透明度混合
                roi = frame[y:y+hzh_h, x:x+hzh_w]
                blended = cv2.addWeighted(roi, 1 - config.hzh_opacity, hzh_frame, config.hzh_opacity, 0)
                frame[y:y+hzh_h, x:x+hzh_w] = blended
        return frame

    @staticmethod
    def scramble_phase(frame: np.ndarray, config: VideoConfig) -> np.ndarray:
        """
        在频域中对视频帧进行扰乱处理。

        参数:
            frame: 当前视频帧
            config: 视频处理配置对象

        返回:
            np.ndarray: 应用频域扰乱后的帧
        """
        if not config.scramble_frequency:
            return frame
        # 将元组转换为列表，以便修改
        channels = list(cv2.split(frame))
        
        # 处理每个通道
        for i in range(len(channels)):
            # 傅里叶变换
            f = np.fft.fft2(channels[i])
            fshift = np.fft.fftshift(f)
            # 获取幅度和相位
            magnitude = np.abs(fshift)
            phase = np.angle(fshift)
            # 扰动相位
            phase += np.random.uniform(-config.scramble_frequency, config.scramble_frequency, phase.shape)
            # 重构频域信号
            fshift_new = magnitude * np.exp(1j * phase)
            f_ishift = np.fft.ifftshift(fshift_new)
            # 逆傅里叶变换并更新通道
            img_back = np.fft.ifft2(f_ishift)
            channels[i] = np.abs(img_back).astype(np.uint8)
        # 合并处理后的通道
        return cv2.merge(channels)
    
    @staticmethod
    def add_texture_noise(frame: np.ndarray, config: VideoConfig) -> np.ndarray:
        """
        为视频帧添加纹理噪声。

        参数:
            frame: 当前视频帧
            config: 视频处理配置对象

        返回:
            np.ndarray: 添加纹理噪声后的帧
        """
        if not config.enable_texture_noise:
            return frame
        # 生成高斯噪声并乘以强度系数
        noise = np.random.normal(0, 1, frame.shape).astype(np.float32) * config.texture_noise_strength
        # 限制噪声范围并转换为整数
        noise = np.clip(noise, -255, 255).astype(np.int16)
        # 将帧转换为 int16 类型以避免溢出
        frame = frame.astype(np.int16)
        frame += noise
        # 裁剪回 uint8 范围
        frame = np.clip(frame, 0, 255).astype(np.uint8)
        return frame

    @staticmethod
    def apply_edge_blur(frame: np.ndarray, config: VideoConfig) -> np.ndarray:
        """
        对视频帧的边缘应用模糊效果。

        参数:
            frame: 当前视频帧
            config: 视频处理配置对象

        返回:
            np.ndarray: 应用边缘模糊后的帧
        """
        if not config.enable_blur_edge:
            return frame
        edges = cv2.Canny(frame, 100, 200)
        blurred = cv2.GaussianBlur(edges, (21, 21), 0)
        return cv2.addWeighted(frame, 0.9, cv2.cvtColor(blurred, cv2.COLOR_GRAY2BGR), 0.1, 0)

    # ========== 2025年新增去重增强效果 ==========
    
    @staticmethod
    def apply_hash_disruption(frame: np.ndarray, config: VideoConfig, frame_idx: int) -> np.ndarray:
        """
        应用感知哈希扰乱效果，通过在边缘添加随机像素和色块干扰pHash/dHash算法。

        参数:
            frame: 当前视频帧
            config: 视频处理配置对象
            frame_idx: 当前帧索引

        返回:
            np.ndarray: 应用感知哈希扰乱后的帧
        """
        if not config.enable_hash_disruption:
            return frame
        
        h, w = frame.shape[:2]
        frame = frame.copy()  # 避免修改原帧
        
        # 1. 在边缘添加随机彩色像素线
        pixel_width = config.hash_disruption_pixels
        
        # 顶部边缘
        for i in range(pixel_width):
            for j in range(w):
                if random.random() < 0.3:  # 30% 概率改变像素
                    frame[i, j] = [random.randint(0, 255) for _ in range(3)]
        
        # 底部边缘
        for i in range(h - pixel_width, h):
            for j in range(w):
                if random.random() < 0.3:
                    frame[i, j] = [random.randint(0, 255) for _ in range(3)]
        
        # 左右边缘
        for i in range(h):
            for j in range(pixel_width):
                if random.random() < 0.3:
                    frame[i, j] = [random.randint(0, 255) for _ in range(3)]
            for j in range(w - pixel_width, w):
                if random.random() < 0.3:
                    frame[i, j] = [random.randint(0, 255) for _ in range(3)]
        
        # 2. 在非显著区域添加半透明微小色块
        for _ in range(config.hash_disruption_blocks):
            # 随机选择边角区域
            corner = random.choice(['tl', 'tr', 'bl', 'br'])
            block_size = config.hash_disruption_block_size
            
            if corner == 'tl':
                x = random.randint(pixel_width, w // 4)
                y = random.randint(pixel_width, h // 4)
            elif corner == 'tr':
                x = random.randint(3 * w // 4, w - block_size - pixel_width)
                y = random.randint(pixel_width, h // 4)
            elif corner == 'bl':
                x = random.randint(pixel_width, w // 4)
                y = random.randint(3 * h // 4, h - block_size - pixel_width)
            else:  # br
                x = random.randint(3 * w // 4, w - block_size - pixel_width)
                y = random.randint(3 * h // 4, h - block_size - pixel_width)
            
            # 确保坐标有效
            x = max(0, min(x, w - block_size))
            y = max(0, min(y, h - block_size))
            
            # 随机颜色和透明度
            color = np.array([random.randint(0, 255) for _ in range(3)], dtype=np.uint8)
            alpha = random.uniform(0.1, 0.3)
            
            # 半透明叠加
            roi = frame[y:y+block_size, x:x+block_size]
            blended = cv2.addWeighted(roi, 1 - alpha, np.full_like(roi, color), alpha, 0)
            frame[y:y+block_size, x:x+block_size] = blended
        
        return frame

    @staticmethod
    def apply_vignette(frame: np.ndarray, config: VideoConfig) -> np.ndarray:
        """
        应用暗角效果，模拟电影质感。

        参数:
            frame: 当前视频帧
            config: 视频处理配置对象

        返回:
            np.ndarray: 应用暗角效果后的帧
        """
        if not config.enable_vignette:
            return frame
        
        h, w = frame.shape[:2]
        
        # 创建暗角遮罩
        Y, X = np.ogrid[:h, :w]
        center_x, center_y = w / 2, h / 2
        
        # 计算到中心的归一化距离
        dist_from_center = np.sqrt((X - center_x) ** 2 + (Y - center_y) ** 2)
        max_dist = np.sqrt(center_x ** 2 + center_y ** 2)
        dist_normalized = dist_from_center / max_dist
        
        # 应用暗角衰减
        vignette_mask = 1 - config.vignette_strength * (dist_normalized / config.vignette_radius) ** 2
        vignette_mask = np.clip(vignette_mask, 0, 1)
        
        # 扩展到3通道
        vignette_mask = np.dstack([vignette_mask] * 3)
        
        # 应用暗角
        frame = (frame.astype(np.float32) * vignette_mask).astype(np.uint8)
        
        return frame

    @staticmethod
    def apply_dynamic_border(frame: np.ndarray, config: VideoConfig, frame_idx: int, total_frames: int) -> np.ndarray:
        """
        应用动态边框效果。

        参数:
            frame: 当前视频帧
            config: 视频处理配置对象
            frame_idx: 当前帧索引
            total_frames: 视频总帧数

        返回:
            np.ndarray: 应用动态边框后的帧
        """
        if not config.enable_dynamic_border or config.border_width <= 0:
            return frame
        
        h, w = frame.shape[:2]
        bw = config.border_width
        
        # 解析颜色
        def hex_to_bgr(hex_color):
            hex_color = hex_color.lstrip('#')
            r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
            return (b, g, r)
        
        progress = frame_idx / max(total_frames, 1)
        
        if config.border_style == 'solid':
            color = hex_to_bgr(config.border_color_start)
            frame[:bw, :] = color  # 顶部
            frame[-bw:, :] = color  # 底部
            frame[:, :bw] = color  # 左边
            frame[:, -bw:] = color  # 右边
            
        elif config.border_style == 'gradient':
            # 渐变颜色
            start_color = np.array(hex_to_bgr(config.border_color_start), dtype=np.float32)
            end_color = np.array(hex_to_bgr(config.border_color_end), dtype=np.float32)
            
            # 随时间变化的渐变
            t = (np.sin(progress * 2 * np.pi) + 1) / 2  # 0-1之间波动
            current_color = tuple((start_color * (1 - t) + end_color * t).astype(np.uint8).tolist())
            
            frame[:bw, :] = current_color
            frame[-bw:, :] = current_color
            frame[:, :bw] = current_color
            frame[:, -bw:] = current_color
            
        elif config.border_style == 'rainbow':
            # 彩虹色，随时间变化
            hue = int((progress * 180) % 180)
            hsv_color = np.array([[[hue, 255, 255]]], dtype=np.uint8)
            bgr_color = cv2.cvtColor(hsv_color, cv2.COLOR_HSV2BGR)[0][0]
            color = tuple(bgr_color.tolist())
            
            frame[:bw, :] = color
            frame[-bw:, :] = color
            frame[:, :bw] = color
            frame[:, -bw:] = color
        
        return frame

    @staticmethod
    def apply_sticker(frame: np.ndarray, config: VideoConfig, frame_idx: int, sticker_cache: dict) -> np.ndarray:
        """
        在视频帧上添加贴纸效果。

        参数:
            frame: 当前视频帧
            config: 视频处理配置对象
            frame_idx: 当前帧索引
            sticker_cache: 贴纸缓存字典

        返回:
            np.ndarray: 添加贴纸后的帧
        """
        if not config.enable_sticker:
            return frame
        
        # 检查贴纸文件夹
        if not os.path.exists(config.sticker_folder):
            return frame
        
        # 获取贴纸文件列表
        sticker_files = [f for f in os.listdir(config.sticker_folder) 
                        if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))]
        if not sticker_files:
            return frame
        
        h, w = frame.shape[:2]
        
        # 根据间隔决定是否切换贴纸
        if config.sticker_change_interval > 0:
            sticker_idx = (frame_idx // config.sticker_change_interval) % len(sticker_files)
        else:
            sticker_idx = sticker_cache.get('sticker_idx', 0)
            if 'sticker_idx' not in sticker_cache:
                sticker_cache['sticker_idx'] = random.randint(0, len(sticker_files) - 1)
                sticker_idx = sticker_cache['sticker_idx']
        
        sticker_file = os.path.join(config.sticker_folder, sticker_files[sticker_idx])
        
        try:
            # 加载贴纸
            sticker = Image.open(sticker_file).convert('RGBA')
            
            # 计算贴纸大小
            scale = random.uniform(*config.sticker_scale_range)
            sticker_w = int(w * scale)
            sticker_h = int(sticker.height * sticker_w / sticker.width)
            sticker = sticker.resize((sticker_w, sticker_h), Image.Resampling.LANCZOS)
            
            # 确定贴纸位置
            margin = 10
            if config.sticker_position == 'corner':
                corner = random.choice(['tl', 'tr', 'bl', 'br'])
                if corner == 'tl':
                    x, y = margin, margin
                elif corner == 'tr':
                    x, y = w - sticker_w - margin, margin
                elif corner == 'bl':
                    x, y = margin, h - sticker_h - margin
                else:
                    x, y = w - sticker_w - margin, h - sticker_h - margin
            else:  # random
                x = random.randint(margin, w - sticker_w - margin)
                y = random.randint(margin, h - sticker_h - margin)
            
            # 确保坐标有效
            x = max(0, min(x, w - sticker_w))
            y = max(0, min(y, h - sticker_h))
            
            # 转换帧为PIL图像
            pil_frame = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert('RGBA')
            
            # 调整贴纸透明度
            sticker_array = np.array(sticker)
            sticker_array[:, :, 3] = (sticker_array[:, :, 3] * config.sticker_opacity).astype(np.uint8)
            sticker = Image.fromarray(sticker_array)
            
            # 叠加贴纸
            pil_frame.paste(sticker, (x, y), sticker)
            
            # 转回OpenCV格式
            frame = cv2.cvtColor(np.array(pil_frame.convert('RGB')), cv2.COLOR_RGB2BGR)
            
        except Exception as e:
            logging.warning(f"贴纸加载失败: {e}")
        
        return frame

    @staticmethod
    def apply_dct_perturbation(frame: np.ndarray, config: VideoConfig) -> np.ndarray:
        """
        应用DCT域扰动，在离散余弦变换域添加微小噪声。

        参数:
            frame: 当前视频帧
            config: 视频处理配置对象

        返回:
            np.ndarray: 应用DCT扰动后的帧
        """
        if not config.enable_dct_perturbation:
            return frame
        
        # 转换为浮点数
        frame_float = frame.astype(np.float32)
        
        # 对每个通道进行DCT扰动
        channels = cv2.split(frame_float)
        perturbed_channels = []
        
        for channel in channels:
            # DCT变换
            dct = cv2.dct(channel)
            
            # 在高频分量添加噪声（避免低频分量影响整体外观）
            h, w = dct.shape
            noise = np.zeros_like(dct)
            # 只在高频区域添加噪声
            noise[h//4:, w//4:] = np.random.uniform(
                -config.dct_noise_strength * 255,
                config.dct_noise_strength * 255,
                (h - h//4, w - w//4)
            )
            dct += noise
            
            # 逆DCT变换
            idct = cv2.idct(dct)
            perturbed_channels.append(idct)
        
        # 合并通道
        frame = cv2.merge(perturbed_channels)
        frame = np.clip(frame, 0, 255).astype(np.uint8)
        
        return frame

class VideoHandler:
    """
    视频处理主类，协调音频和视频的处理流程。
    """
    def __init__(self, config: VideoConfig):
        """
        初始化视频处理器，验证配置。

        参数:
            config: 视频处理配置对象
        """
        self.config = config
        self.config.validate()
        self.subs = None        # 字幕对象，延迟到 process_video 中加载
        self.batch_size = min(100, max(10, os.cpu_count() * 10))  # 动态调整
        self.sticker_cache = {}  # 贴纸缓存

        # 预加载图片水印
        self.watermark_img = None
        self.wm_rgb = None
        self.wm_alpha = None
        if config.watermark_type == 'image' and config.watermark_image_path:
            self.watermark_img = Image.open(config.watermark_image_path).convert("RGBA")

    def process_video(self, input_path: str, output_path: str) -> None:
        """
        处理整个视频，包括音频和视频的处理，并将结果保存。

        参数:
            input_path: 输入视频文件路径
            output_path: 输出视频文件路径
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"输入视频 {input_path} 不存在")
        
        # 检查并启用 GPU 加速
        if self.config.enable_gpu:
            try:
                cv2.ocl.setUseOpenCL(True)
                logging.info("GPU 加速已启用")
            except Exception as e:
                logging.warning(f"启用 GPU 加速失败: {str(e)}")
        
        video_stream, audio_stream = FFmpegHandler.split_av_streams(input_path)
        width, height, fps = FFmpegHandler.get_video_properties(input_path)
        cap = cv2.VideoCapture(input_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        temp_files = []
        subtitles_file = None

        try:
            # 随机决定是否水平镜像
            if self.config.enable_random_flip:
                self.config.flip_horizontal = random.choice([True, False])
                logging.info(f"随机水平镜像: {'启用' if self.config.flip_horizontal else '禁用'}")

            # 随机决定视频加速倍率
            speed_factor = 1.0
            if self.config.enable_speed_change:
                speed_factor = random.uniform(*self.config.speed_change_range)
                logging.info(f"随机视频加速倍率: {speed_factor:.3f}")

            # 预处理图片水印大小
            if self.config.watermark_type == 'image' and self.watermark_img:
                wm_width = width // 5
                wm_height = int(wm_width * self.watermark_img.height / self.watermark_img.width)
                self.watermark_img = self.watermark_img.resize((wm_width, wm_height), Image.Resampling.LANCZOS)
                wm_array = np.array(self.watermark_img)
                self.wm_rgb = cv2.cvtColor(wm_array[:, :, :3], cv2.COLOR_RGB2BGR)
                self.wm_alpha = wm_array[:, :, 3] / 255.0 * self.config.watermark_opacity
            # 获取视频时长并根据 subtitles_duration 决定是否加载字幕
            probe = ffmpeg.probe(input_path)
            duration = float(probe['format']['duration'])
            if self.config.include_subtitles and duration > self.config.subtitles_duration:
                if self.config.use_whisper:
                    subtitles_file = SubtitleHandler.generate_subtitles(input_path, self.config.whisper_model_name)
                    temp_files.append(subtitles_file)
                    logging.info(f"使用 Whisper 生成字幕: {subtitles_file}")
                else:
                    subtitles_file = self.config.subtitles_file
                
                if subtitles_file and os.path.exists(subtitles_file):
                    self.subs = pysrt.open(subtitles_file)
                    logging.info(f"字幕文件已加载: {subtitles_file}")
                else:
                    logging.warning(f"字幕文件 {subtitles_file} 不存在，跳过字幕加载")
                    self.subs = None
            else:
                logging.info(f"不添加字幕：include_subtitles={self.config.include_subtitles}, duration={duration}, subtitles_duration={self.config.subtitles_duration}")
                self.subs = None

            # 处理音频
            audio_path = tempfile.mktemp(suffix='.wav')
            temp_files.append(audio_path)
            if audio_stream:
                audio_stream.output(audio_path, format='wav').run(overwrite_output=True)
                processed_audio_path = AudioHandler.remove_silence(audio_path, self.config)
                temp_files.append(processed_audio_path)
                
                # 2025新增：音频指纹扰乱
                if self.config.enable_audio_fingerprint_disrupt:
                    disrupted_audio_path = AudioFingerprintDisruptor.disrupt_audio(processed_audio_path, self.config)
                    temp_files.append(disrupted_audio_path)
                    processed_audio_path = disrupted_audio_path
                
                if self.config.include_background_music and self.config.background_music_file and os.path.exists(self.config.background_music_file):
                    mixed_audio_path = AudioHandler.mix_bgm(processed_audio_path, self.config.background_music_file, self.config.background_music_volume)
                    temp_files.append(mixed_audio_path)
                    audio_stream = ffmpeg.input(mixed_audio_path)
                else:
                    audio_stream = ffmpeg.input(processed_audio_path)
                
                # 应用音频加速滤镜
                if speed_factor != 1.0:
                    try:
                        audio_stream = audio_stream.filter('atempo', speed_factor)
                        logging.info(f"应用音频加速滤镜: atempo={speed_factor:.3f}")
                    except Exception as e:
                        logging.warning(f"应用音频加速滤镜失败: {e}，将使用原速音频")


            # 定义帧交换索引映射函数
            def get_original_idx(output_idx, interval, total_frames):
                if interval <= 0 or not self.config.enable_frame_swap:
                    return output_idx
                k = output_idx // interval
                if output_idx % interval == 0 and k * interval + 1 < total_frames:
                    return k * interval + 1
                elif output_idx % interval == 1 and k * interval + 1 < total_frames:
                    return k * interval
                else:
                    return output_idx

            # 定义交换帧生成器
            def swapped_frame_generator(cap, total_frames, interval):
                output_idx = 0
                while output_idx < total_frames:
                    original_idx = get_original_idx(output_idx, interval, total_frames)
                    cap.set(cv2.CAP_PROP_POS_FRAMES, original_idx)
                    ret, frame = cap.read()
                    if ret:
                        yield output_idx, frame
                        output_idx += 1
                    else:
                        break

            # 根据 enable_frame_swap 选择帧生成器
            if self.config.enable_frame_swap:
                frame_generator = swapped_frame_generator(cap, total_frames, self.config.frame_swap_interval)
            else:
                frame_generator = self._frame_generator(cap)

            # 分批处理视频帧
            processed_frame_generator = self._process_frames(frame_generator, total_frames, fps, height, width)
            self._write_frames(processed_frame_generator, output_path, width, height, fps, audio_stream, speed_factor)

        finally:
            cap.release()
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    os.remove(temp_file)

    def _frame_generator(self, cap: cv2.VideoCapture) -> Generator[Tuple[int, np.ndarray], None, None]:
        """
        生成器：逐帧读取视频帧。

        参数:
            cap: OpenCV 视频捕获对象

        返回:
            Generator[Tuple[int, np.ndarray], None, None]: 帧索引和帧数据的生成器
        """
        frame_idx = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            yield frame_idx, frame
            frame_idx += 1

    def _process_frames(self, frame_generator: Generator[Tuple[int, np.ndarray], None, None], 
                        total_frames: int, fps: float, orig_height: int, orig_width: int) -> Generator[np.ndarray, None, None]:
        """
        分批处理视频帧，并返回处理后的帧生成器。

        参数:
            frame_generator: 原始帧生成器
            total_frames: 视频总帧数
            fps: 视频帧率
            orig_height: 原始视频高度
            orig_width: 原始视频宽度

        返回:
            Generator[np.ndarray, None, None]: 处理后的帧生成器
        """
        batch = []
        for frame_idx, frame in frame_generator:
            batch.append((frame_idx, frame))
            if len(batch) >= self.batch_size:
                processed_batch = self._process_batch(batch, total_frames, fps, orig_height, orig_width)
                for _, processed_frame in processed_batch:
                    yield processed_frame
                batch = []
        if batch:
            processed_batch = self._process_batch(batch, total_frames, fps, orig_height, orig_width)
            for _, processed_frame in processed_batch:
                yield processed_frame

    def _process_batch(self, batch: List[Tuple[int, np.ndarray]], total_frames: int, fps: float, 
                       orig_height: int, orig_width: int) -> List[Tuple[int, np.ndarray]]:
        """
        并行处理一批视频帧。

        参数:
            batch: 待处理的帧批次
            total_frames: 视频总帧数
            fps: 视频帧率
            orig_height: 原始视频高度
            orig_width: 原始视频宽度

        返回:
            List[Tuple[int, np.ndarray]]: 处理后的帧列表，按帧索引排序
        """
        with ThreadPoolExecutor(max_workers=min(4, os.cpu_count())) as executor:
            futures = [executor.submit(self._process_single_frame, frame, idx, self.config, fps, total_frames, orig_height, orig_width)
                       for idx, frame in batch]
            return sorted([f.result() for f in futures], key=lambda x: x[0])

    def _process_single_frame(self, frame: np.ndarray, frame_idx: int, config: VideoConfig, 
                          fps: float, total_frames: int, orig_height: int, orig_width: int) -> Tuple[int, np.ndarray]:
        """
        处理单个视频帧，应用所有特效。
        
        参数:
            frame: 当前视频帧
            frame_idx: 当前帧索引
            config: 视频处理配置对象
            fps: 视频帧率
            total_frames: 视频总帧数
            orig_height: 原始视频高度
            orig_width: 原始视频宽度
        
        返回:
            Tuple[int, np.ndarray]: 帧索引和处理后的帧
        """
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        if config.flip_horizontal:
            frame = cv2.flip(frame, 1)
        frame = VideoEffects.rotate_frame(frame, config)
        h, w = frame.shape[:2]
        
        # 应用按比例裁剪
        crop_h = int(orig_height * config.crop_percentage)
        crop_w = int(orig_width * config.crop_percentage)
        top, bottom, left, right = crop_h, crop_h, crop_w, crop_w
        if top + bottom < h and left + right < w:
            frame = frame[top:h - bottom, left:w - right]
        
        # 缩放回原始尺寸
        if frame.shape[0] != orig_height or frame.shape[1] != orig_width:
            frame = cv2.resize(frame, (orig_width, orig_height), interpolation=cv2.INTER_AREA)
        
        frame = VideoEffects.adjust_sbc(frame, config)
        if config.include_watermark:
            frame = VideoEffects.add_watermark(frame, config, frame_idx, total_frames, self)  # 传递 self
        if self.config.include_subtitles and self.subs:
            frame = VideoEffects.add_subtitles(frame, config, frame_idx, fps, self.subs)
        if self.config.include_titles:
            frame = VideoEffects.add_titles(frame, config)
        frame = VideoEffects.add_hzh_effect(frame, config, frame_idx, total_frames)
        frame = VideoEffects.color_shift(frame, config)
        frame = VideoEffects.blur_background(frame, config)
        frame = VideoEffects.scramble_phase(frame, config)
        frame = VideoEffects.add_texture_noise(frame, config)
        frame = VideoEffects.apply_edge_blur(frame, config)
        frame = VideoEffects.apply_gaussian_blur(frame, config, frame_idx)
        frame = VideoEffects.apply_fade_effect(frame, config, frame_idx, total_frames)
        
        # ========== 2025年新增去重增强效果 ==========
        frame = VideoEffects.apply_hash_disruption(frame, config, frame_idx)  # 感知哈希扰乱
        frame = VideoEffects.apply_vignette(frame, config)  # 暗角效果
        frame = VideoEffects.apply_dynamic_border(frame, config, frame_idx, total_frames)  # 动态边框
        frame = VideoEffects.apply_sticker(frame, config, frame_idx, self.sticker_cache)  # 贴纸叠加
        frame = VideoEffects.apply_dct_perturbation(frame, config)  # DCT域扰动
        
        return (frame_idx, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))

    def _write_frames(self, frame_generator: Generator[np.ndarray, None, None], output_path: str, 
                      width: int, height: int, fps: float, audio_stream: ffmpeg.Stream, speed_factor: float = 1.0) -> None:
        """
        将处理后的帧写入输出视频。

        参数:
            frame_generator: 处理后的帧生成器
            output_path: 输出视频文件路径
            width: 原始视频宽度
            height: 原始视频高度
            fps: 视频帧率
            audio_stream: 处理后的音频流（可能为 None）
        """
        first_frame = next(frame_generator)
        adjusted_width, adjusted_height = first_frame.shape[1], first_frame.shape[0]
        video_stream = ffmpeg.input('pipe:', format='rawvideo', pix_fmt='bgr24', 
                                    s=f'{adjusted_width}x{adjusted_height}', framerate=fps)
        
        # 根据是否有音频流选择不同的输出配置
        # 使用 yuv420p 像素格式和 high profile 确保最佳兼容性
        if audio_stream is not None:
            # 有音频流时，同时输出视频和音频
            output = ffmpeg.output(
                video_stream, audio_stream, output_path, 
                vcodec='libx264', acodec='aac', preset='fast', 
                pix_fmt='yuv420p', profile='high',
                crf=23, r=fps * speed_factor, s=f'{adjusted_width}x{adjusted_height}',
                **{'b:v': '2M'}
            )
        else:
            # 无音频流时，只输出视频（不设置 acodec）
            output = video_stream.output(
                output_path, 
                vcodec='libx264', preset='fast',
                pix_fmt='yuv420p', profile='high',
                crf=23, r=fps * speed_factor, s=f'{adjusted_width}x{adjusted_height}',
                **{'b:v': '2M'}
            )
        
        process = output.overwrite_output().run_async(pipe_stdin=True)
        
        # ========== 2025新增：时间轴随机化 - 片头帧 ==========
        if self.config.enable_timeline_randomize and self.config.add_intro_frames > 0:
            intro_frame = self._generate_intro_outro_frame(first_frame, self.config.intro_outro_color)
            for _ in range(self.config.add_intro_frames):
                process.stdin.write(intro_frame.tobytes())
            logging.info(f"已添加 {self.config.add_intro_frames} 个片头帧")
        
        # 写入第一帧
        process.stdin.write(first_frame.tobytes())
        
        # 写入后续帧（支持随机丢帧和复制帧）
        last_frame = first_frame
        frame_count = 1
        dropped_count = 0
        duplicated_count = 0
        
        for frame in frame_generator:
            # 时间轴随机化：随机丢帧
            if self.config.enable_timeline_randomize and self.config.frame_drop_ratio > 0:
                if random.random() < self.config.frame_drop_ratio:
                    dropped_count += 1
                    continue  # 跳过此帧
            
            process.stdin.write(frame.tobytes())
            frame_count += 1
            
            # 时间轴随机化：随机复制帧
            if self.config.enable_timeline_randomize and self.config.frame_duplicate_ratio > 0:
                if random.random() < self.config.frame_duplicate_ratio:
                    process.stdin.write(frame.tobytes())
                    duplicated_count += 1
            
            last_frame = frame
        
        # ========== 2025新增：时间轴随机化 - 片尾帧 ==========
        if self.config.enable_timeline_randomize and self.config.add_outro_frames > 0:
            outro_frame = self._generate_intro_outro_frame(last_frame, self.config.intro_outro_color)
            for _ in range(self.config.add_outro_frames):
                process.stdin.write(outro_frame.tobytes())
            logging.info(f"已添加 {self.config.add_outro_frames} 个片尾帧")
        
        if dropped_count > 0 or duplicated_count > 0:
            logging.info(f"时间轴随机化: 丢弃 {dropped_count} 帧, 复制 {duplicated_count} 帧")
        
        process.stdin.close()
        process.wait()
        logging.info(f"视频处理完成，输出到 {output_path}")
        
        # ========== 2025新增：元数据清洗 ==========
        if self.config.enable_metadata_clean:
            MetadataHandler.clean_metadata(output_path, self.config)

    def _generate_intro_outro_frame(self, reference_frame: np.ndarray, color_mode: str) -> np.ndarray:
        """
        生成片头或片尾帧。

        参数:
            reference_frame: 参考帧（用于获取尺寸和blur模式）
            color_mode: 颜色模式 - 'black', 'white', 'blur'

        返回:
            np.ndarray: 生成的帧
        """
        h, w = reference_frame.shape[:2]
        
        if color_mode == 'black':
            return np.zeros((h, w, 3), dtype=np.uint8)
        elif color_mode == 'white':
            return np.ones((h, w, 3), dtype=np.uint8) * 255
        elif color_mode == 'blur':
            # 使用参考帧的高度模糊版本
            return cv2.GaussianBlur(reference_frame, (51, 51), 0)
        else:
            return np.zeros((h, w, 3), dtype=np.uint8)

if __name__ == "__main__":
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description="python3 dedup.py -i input.mp4 -o output.mp4")
    parser.add_argument("-i", "--input", default="input.mp4", help="输入视频文件路径 (默认: input.mp4)")
    parser.add_argument("-o", "--output", default="output.mp4", help="输出视频文件路径 (默认: output.mp4)")
    
    # 解析命令行参数
    args = parser.parse_args()
    
    # 创建配置对象
    config = VideoConfig()
    # 初始化视频处理器
    processor = VideoHandler(config)
    # 处理视频并保存
    processor.process_video(args.input, args.output)