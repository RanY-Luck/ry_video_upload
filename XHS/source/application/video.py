from .request import Html

__all__ = ["Video"]

from ..expansion import Namespace


class Video:
    VIDEO_LINK = (
        "video",
        "consumer",
        "originVideoKey",
    )

    @classmethod
    def deal_video_link(
        cls,
        data: Namespace,
        preference="resolution",
    ):
        return cls.generate_video_link(data) or cls.get_video_link(data, preference)

    @classmethod
    def generate_video_link(cls, data: Namespace) -> list:
        # 优先尝试直接获取 originVideoKey
        if t := data.safe_extract(".".join(cls.VIDEO_LINK)):
            return [Html.format_url(f"https://sns-video-bd.xhscdn.com/{t}")]
        
        # 如果获取失败，尝试从 h264 masterUrl 中提取 key
        # 通常 masterUrl 格式为: http://sns-video-qn.xhscdn.com/stream/VIDEO_KEY/h264/...
        # 或者直接是 key 的一部分
        try:
            items = cls.get_video_items(data)
            if items:
                master_url = items[0].masterUrl
                if "/stream/" in master_url:
                    # 尝试提取 stream 后的部分作为 key
                    # 注意: 这是一种尝试性的回退策略
                    parts = master_url.split("/stream/")
                    if len(parts) > 1:
                        key_part = parts[1].split("/")[0]
                        # 只有当 key 看起来像是一个有效的 ID 时才使用
                        if len(key_part) > 10: 
                             return [Html.format_url(f"https://sns-video-bd.xhscdn.com/{key_part}")]
        except Exception:
            pass
            
        return []

    @classmethod
    def get_video_link(
        cls,
        data: Namespace,
        preference="resolution",
    ) -> list:
        if not (items := cls.get_video_items(data)):
            return []
        match preference:
            case "resolution":
                items.sort(key=lambda x: x.height)
            case "bitrate" | "size":
                items.sort(key=lambda x: x.preference)
            case _:
                raise ValueError(f"Invalid video preference value: {preference}")
        return [b[0]] if (b := items[-1].backupUrls) else [items[-1].masterUrl]

    @staticmethod
    def get_video_items(data: Namespace) -> list:
        h264 = data.safe_extract("video.media.stream.h264")
        h265 = data.safe_extract("video.media.stream.h265")
        return [*h264, *h265]
