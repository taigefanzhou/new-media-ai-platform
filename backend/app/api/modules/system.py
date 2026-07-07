from __future__ import annotations

from app.api.module_registry import api_module_manifest
from app.api.modules._legacy import legacy_module_router
from app.services.export_profiles import export_profile_options
from app.services.product_modules import product_module_manifest
from app.services.video_skills import video_skill_manifest


MIGRATED_PATHS = {
    "/video-export-profiles",
    "/video-production-skills",
    "/product-modules",
}

router = legacy_module_router("system", exclude_paths=MIGRATED_PATHS)


@router.get("/video-export-profiles")
def list_video_export_profiles() -> list[dict[str, object]]:
    return export_profile_options()


@router.get("/video-production-skills")
def list_video_production_skills() -> dict[str, object]:
    return {
        "enabled": True,
        "mode": "built_in",
        "pipeline": [
            "参考拆解",
            "原创脚本",
            "分镜执行表",
            "素材匹配",
            "视频生成",
            "字幕包装",
            "质量检查",
        ],
        "skills": video_skill_manifest(),
    }


@router.get("/product-modules")
def list_product_modules() -> dict[str, object]:
    return {
        "version": "2026-07-06",
        "architecture": "modular_video_production",
        "navigation": [
            "参考视频学习生成",
            "输入方向自动创作",
            "素材库与数字人",
            "视频库与生成任务",
            "账号绑定与自动发布",
        ],
        "modules": product_module_manifest(),
        "api_modules": api_module_manifest(),
    }
