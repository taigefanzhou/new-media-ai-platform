from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ApiModule:
    key: str
    label: str
    description: str
    prefixes: tuple[str, ...]


API_MODULES: tuple[ApiModule, ...] = (
    ApiModule(
        key="system",
        label="系统与认证",
        description="登录、微信扫码、账号设置、模型配置、集成状态和系统总览。",
        prefixes=(
            "/health",
            "/auth",
            "/settings",
            "/dashboard",
            "/integrations",
            "/product-modules",
            "/video-production-skills",
            "/video-export-profiles",
        ),
    ),
    ApiModule(
        key="reference_learning",
        label="参考视频学习",
        description="参考素材导入、链接解析、转写、深度拆解和从参考生成脚本。",
        prefixes=(
            "/materials",
            "/reference-materials",
            "/transcriptions",
            "/video-analyses",
        ),
    ),
    ApiModule(
        key="script_creation",
        label="脚本方向创作",
        description="主题、脚本生成、批量脚本和脚本更新。",
        prefixes=(
            "/topics",
            "/scripts",
        ),
    ),
    ApiModule(
        key="digital_humans",
        label="素材库与数字人",
        description="数字人资产、真人认证和火山人像认证回调。",
        prefixes=(
            "/digital-humans",
            "/volcengine/portrait-auth",
        ),
    ),
    ApiModule(
        key="drama",
        label="短剧工作台",
        description="短剧项目、角色卡、场景卡、逐镜头生产和视频任务创建。",
        prefixes=("/drama-projects", "/drama-shots"),
    ),
    ApiModule(
        key="video_library",
        label="视频库与生成任务",
        description="视频任务、分段素材、成片输出、审核和发布准备。",
        prefixes=(
            "/video-tasks",
        ),
    ),
    ApiModule(
        key="trending",
        label="主题采集",
        description="短视频平台选题采集和爆款参考入库。",
        prefixes=(
            "/trending",
        ),
    ),
    ApiModule(
        key="publishing",
        label="账号绑定与自动发布",
        description="平台账号、发布记录和发布状态管理。",
        prefixes=(
            "/publish-records",
            "/platform-accounts",
        ),
    ),
)


def api_module_manifest() -> list[dict[str, object]]:
    return [asdict(module) for module in API_MODULES]


def api_module_by_key(key: str) -> ApiModule:
    for module in API_MODULES:
        if module.key == key:
            return module
    raise KeyError(f"Unknown API module: {key}")


def module_for_path(path: str) -> ApiModule:
    for module in API_MODULES:
        if any(path == prefix or path.startswith(f"{prefix}/") for prefix in module.prefixes):
            return module
    return API_MODULES[0]
