from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExportProfile:
    key: str
    label: str
    platform: str
    width: int
    height: int
    aspect_ratio: str
    generation_ratio: str
    fit_mode: str
    max_duration_seconds: int
    max_size_mb: int
    notes: str


EXPORT_PROFILES: dict[str, ExportProfile] = {
    "douyin_vertical": ExportProfile(
        key="douyin_vertical",
        label="抖音竖版 9:16",
        platform="douyin",
        width=1080,
        height=1920,
        aspect_ratio="9:16",
        generation_ratio="9:16",
        fit_mode="crop",
        max_duration_seconds=900,
        max_size_mb=4096,
        notes="适合抖音主信息流，默认作为短视频成片规格。",
    ),
    "wechat_channels_vertical": ExportProfile(
        key="wechat_channels_vertical",
        label="视频号竖版 6:7",
        platform="wechat_channels",
        width=1080,
        height=1260,
        aspect_ratio="6:7",
        generation_ratio="9:16",
        fit_mode="contain_blur",
        max_duration_seconds=3600,
        max_size_mb=2048,
        notes="适合视频号信息流；保留完整竖版内容，用柔化背景补齐 6:7 画布。",
    ),
    "wechat_channels_portrait": ExportProfile(
        key="wechat_channels_portrait",
        label="视频号全屏竖版 9:16",
        platform="wechat_channels",
        width=1080,
        height=1920,
        aspect_ratio="9:16",
        generation_ratio="9:16",
        fit_mode="crop",
        max_duration_seconds=3600,
        max_size_mb=2048,
        notes="适合人物口播、行业干货和全屏竖版参考模板。",
    ),
    "wechat_channels_landscape": ExportProfile(
        key="wechat_channels_landscape",
        label="视频号横版 16:9",
        platform="wechat_channels",
        width=1920,
        height=1080,
        aspect_ratio="16:9",
        generation_ratio="16:9",
        fit_mode="contain_blur",
        max_duration_seconds=3600,
        max_size_mb=2048,
        notes="适合新闻评论、资料讲解和横版参考视频改写。",
    ),
    "archive_landscape": ExportProfile(
        key="archive_landscape",
        label="横版资料版 16:9",
        platform="manual",
        width=1920,
        height=1080,
        aspect_ratio="16:9",
        generation_ratio="16:9",
        fit_mode="contain_blur",
        max_duration_seconds=3600,
        max_size_mb=4096,
        notes="适合内部资料、官网或长视频平台使用。",
    ),
}


DEFAULT_PROFILE_BY_PLATFORM = {
    "douyin": "douyin_vertical",
    "wechat_channels": "wechat_channels_vertical",
    "xiaohongshu": "douyin_vertical",
    "kuaishou": "douyin_vertical",
    "manual": "archive_landscape",
}


def default_export_profile_key(platform: str | None = None) -> str:
    return DEFAULT_PROFILE_BY_PLATFORM.get(str(platform or "").strip(), "douyin_vertical")


def resolve_export_profile(profile_key: str | None = None, platform: str | None = None) -> ExportProfile:
    key = str(profile_key or "").strip() or default_export_profile_key(platform)
    return EXPORT_PROFILES.get(key) or EXPORT_PROFILES[default_export_profile_key(platform)]


def export_profile_options() -> list[dict[str, object]]:
    return [
        {
            "key": profile.key,
            "label": profile.label,
            "platform": profile.platform,
            "width": profile.width,
            "height": profile.height,
            "aspect_ratio": profile.aspect_ratio,
            "generation_ratio": profile.generation_ratio,
            "fit_mode": profile.fit_mode,
            "max_duration_seconds": profile.max_duration_seconds,
            "max_size_mb": profile.max_size_mb,
            "notes": profile.notes,
        }
        for profile in EXPORT_PROFILES.values()
    ]
