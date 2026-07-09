from __future__ import annotations

from fastapi import APIRouter

from app.api.module_registry import api_module_manifest
from app.api.system_status import dashboard, integrations_status, test_link_resolver
from app.api.system_models import (
    activate_model_config,
    activate_platform_credential,
    create_model_config,
    create_platform_credential,
    list_model_configs,
    list_platform_credentials,
    model_diagnostics,
    model_usage_summary,
    test_model_config,
    update_model_config,
    update_platform_credential,
)
from app.api.system_auth import change_password, health, login, logout, me
from app.api.system_storage import (
    remote_upload_settings,
    update_remote_upload_settings,
    update_video_storage,
    video_storage_summary,
)
from app.api.system_users import create_user, list_users, reset_user_password, update_user
from app.api.system_wechat import (
    approve_wechat_login_request,
    disable_wechat_identity,
    get_wechat_login_config,
    list_wechat_identities,
    list_wechat_login_requests,
    reject_wechat_login_request,
    save_wechat_login_config,
    start_wechat_login,
    wechat_login_callback,
    wechat_login_public_config,
)
from app.schemas.requests import (
    AIModelConfigPublic,
    PlatformCredentialPublic,
    UserPublic,
    WechatIdentityPublic,
    WechatLoginConfigPublic,
    WechatLoginPublicConfig,
    WechatLoginRequestPublic,
)
from app.services.export_profiles import export_profile_options
from app.services.product_modules import product_module_manifest
from app.services.video_skills import video_skill_manifest


router = APIRouter(tags=["系统与认证"])


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


router.get("/health")(health)
router.post("/auth/login")(login)
router.get("/auth/me")(me)
router.post("/auth/logout")(logout)
router.post("/auth/change-password")(change_password)
router.get("/auth/wechat/config", response_model=WechatLoginPublicConfig)(wechat_login_public_config)
router.get("/auth/wechat/start")(start_wechat_login)
router.get("/auth/wechat/callback")(wechat_login_callback)
router.get("/settings/wechat-login/config", response_model=WechatLoginConfigPublic)(get_wechat_login_config)
router.post("/settings/wechat-login/config", response_model=WechatLoginConfigPublic)(save_wechat_login_config)
router.get("/settings/wechat-login/requests", response_model=list[WechatLoginRequestPublic])(list_wechat_login_requests)
router.post("/settings/wechat-login/requests/{request_id}/approve", response_model=WechatLoginRequestPublic)(approve_wechat_login_request)
router.post("/settings/wechat-login/requests/{request_id}/reject", response_model=WechatLoginRequestPublic)(reject_wechat_login_request)
router.get("/settings/wechat-login/identities", response_model=list[WechatIdentityPublic])(list_wechat_identities)
router.post("/settings/wechat-login/identities/{identity_id}/disable", response_model=WechatIdentityPublic)(disable_wechat_identity)
router.get("/settings/users", response_model=list[UserPublic])(list_users)
router.post("/settings/users", response_model=UserPublic)(create_user)
router.patch("/settings/users/{user_id}", response_model=UserPublic)(update_user)
router.post("/settings/users/{user_id}/reset-password", response_model=UserPublic)(reset_user_password)
router.get("/dashboard")(dashboard)
router.get("/settings/models", response_model=list[AIModelConfigPublic])(list_model_configs)
router.get("/settings/model-diagnostics")(model_diagnostics)
router.get("/settings/model-usage")(model_usage_summary)
router.get("/settings/video-storage")(video_storage_summary)
router.patch("/settings/video-storage")(update_video_storage)
router.get("/settings/remote-upload")(remote_upload_settings)
router.patch("/settings/remote-upload")(update_remote_upload_settings)
router.post("/settings/models", response_model=AIModelConfigPublic)(create_model_config)
router.patch("/settings/models/{model_id}", response_model=AIModelConfigPublic)(update_model_config)
router.post("/settings/models/{model_id}/activate", response_model=AIModelConfigPublic)(activate_model_config)
router.post("/settings/models/{model_id}/test")(test_model_config)
router.get("/settings/platform-credentials", response_model=list[PlatformCredentialPublic])(list_platform_credentials)
router.post("/settings/platform-credentials", response_model=PlatformCredentialPublic)(create_platform_credential)
router.patch("/settings/platform-credentials/{credential_id}", response_model=PlatformCredentialPublic)(update_platform_credential)
router.post("/settings/platform-credentials/{credential_id}/activate", response_model=PlatformCredentialPublic)(activate_platform_credential)
router.post("/settings/link-resolver/test")(test_link_resolver)
router.get("/integrations/status")(integrations_status)
