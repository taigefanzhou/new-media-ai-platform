from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from app.models.entities import CopyrightStatus, MaterialKind, PublishPlatform, TrendingSource, UserRole


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6)


class AIModelConfigCreate(BaseModel):
    name: str
    provider: str
    purpose: str = "script"
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    model_name: str
    is_active: bool = False
    notes: str = ""


class AIModelConfigUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    purpose: Optional[str] = None
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class AIModelConfigPublic(BaseModel):
    id: int
    name: str
    provider: str
    purpose: str
    api_base: Optional[str] = None
    model_name: str
    is_active: bool
    notes: str = ""
    created_at: datetime
    has_api_key: bool


class UserCreate(BaseModel):
    username: str
    password: str = Field(..., min_length=6)
    role: UserRole = UserRole.operator
    is_active: bool = True


class UserUpdate(BaseModel):
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserPasswordReset(BaseModel):
    password: str = Field(..., min_length=6)


class UserPublic(BaseModel):
    id: int
    username: str
    role: UserRole
    is_active: bool
    created_at: datetime


class StorageSettingsUpdate(BaseModel):
    storage_root: str = Field(..., min_length=1)


class RemoteUploadSettingsUpdate(BaseModel):
    enabled: bool = False
    upload_url: Optional[str] = None
    public_base_url: Optional[str] = None
    file_field_name: str = "file"
    upload_token: Optional[str] = None
    clear_upload_token: bool = False


class TrendingSearchCreate(BaseModel):
    platform: TrendingSource
    keyword: str
    category: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=100)
    min_like_count: int = Field(default=0, ge=0)
    min_comment_count: int = Field(default=0, ge=0)
    sort_by: str = "engagement"
    notes: str = ""


class TrendingVideoCreate(BaseModel):
    platform: TrendingSource
    title: str
    source_url: str
    author: Optional[str] = None
    hook: str = ""
    summary: str = ""
    tags: str = ""


class TranscriptionTaskCreate(BaseModel):
    material_id: int
    language: str = "zh-CN"


class ReferenceVideoAnalysisCreate(BaseModel):
    material_id: int
    provider: str = "local"
    language: str = "zh-CN"


class MaterialCreate(BaseModel):
    name: str
    kind: MaterialKind
    copyright_status: CopyrightStatus = CopyrightStatus.owned
    source_url: Optional[str] = None
    tags: str = ""


class ReferenceMaterialLinkCreate(BaseModel):
    source_url: str = Field(..., min_length=8)
    title: Optional[str] = None
    platform: str = "auto"
    tags: str = ""
    download: bool = True


class TopicCreate(BaseModel):
    title: str
    industry: Optional[str] = None
    product_line: Optional[str] = None
    audience: Optional[str] = None
    reference_material_id: Optional[int] = None
    notes: str = ""


class ScriptGenerateRequest(BaseModel):
    topic_id: Optional[int] = None
    topic: str = Field(..., description="选题或产品卖点")
    brand_voice: str = "专业、可信、短视频口播风格"
    duration_seconds: int = Field(default=30, ge=15, le=360)
    target_platform: str = "douyin"
    output_language: str = "zh-CN"


class ScriptBatchGenerateRequest(ScriptGenerateRequest):
    count: int = Field(default=3, ge=1, le=20)
    topics: list[str] = Field(default_factory=list)


class ScriptUpdate(BaseModel):
    hook: Optional[str] = None
    voiceover: Optional[str] = None
    storyboard: Optional[str] = None
    storyboard_plan: Optional[str] = None
    seedance_prompt: Optional[str] = None
    title_options: Optional[str] = None
    hashtags: Optional[str] = None
    compliance_notes: Optional[str] = None


class DigitalHumanCreate(BaseModel):
    name: str
    role: Optional[str] = None
    style: str = "business"
    portrait_material_id: Optional[int] = None
    source_video_material_id: Optional[int] = None
    default_voice: Optional[str] = None
    authorization_scope: str = "internal_marketing"


class VolcenginePortraitAuthSessionCreate(BaseModel):
    callback_url: Optional[str] = None
    subject_name: Optional[str] = None
    remark: str = ""


class VideoTaskCreate(BaseModel):
    script_id: int
    digital_human_id: Optional[int] = None
    production_mode: str = "talking_head_template"
    target_platform: Optional[str] = None
    export_profile: Optional[str] = None
    subtitle_enabled: bool = True
    subtitle_style: str = "auto"


class ScriptVideoTaskCreate(BaseModel):
    digital_human_id: Optional[int] = None
    production_mode: str = "talking_head_template"
    target_platform: Optional[str] = None
    export_profile: Optional[str] = None
    subtitle_enabled: bool = True
    subtitle_style: str = "auto"


class VideoTaskBatchCreateRequest(BaseModel):
    script_ids: list[int] = Field(..., min_length=1, max_length=50)
    digital_human_id: Optional[int] = None
    production_mode: str = "talking_head_template"
    target_platform: Optional[str] = None
    export_profile: Optional[str] = None
    subtitle_enabled: bool = True
    subtitle_style: str = "auto"


class VideoTaskBatchRunRequest(BaseModel):
    task_ids: list[int] = Field(..., min_length=1, max_length=20)


class VideoSegmentMaterialUpdate(BaseModel):
    material_id: Optional[int] = None


class PlatformAccountCreate(BaseModel):
    platform: PublishPlatform
    account_name: str
    owner: Optional[str] = None
    status: str = "active"
    is_default: bool = False
    notes: str = ""


class PlatformAccountUpdate(BaseModel):
    platform: Optional[PublishPlatform] = None
    account_name: Optional[str] = None
    owner: Optional[str] = None
    status: Optional[str] = None
    is_default: Optional[bool] = None
    notes: Optional[str] = None


class PlatformCredentialCreate(BaseModel):
    platform: PublishPlatform
    purpose: str = "publishing"
    display_name: str
    api_base: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    webhook_url: Optional[str] = None
    status: str = "draft"
    is_active: bool = False
    notes: str = ""


class PlatformCredentialUpdate(BaseModel):
    platform: Optional[PublishPlatform] = None
    purpose: Optional[str] = None
    display_name: Optional[str] = None
    api_base: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    webhook_url: Optional[str] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class LinkResolverTestRequest(BaseModel):
    source_url: str = Field(..., min_length=8)
    platform: str = "auto"


class PlatformCredentialPublic(BaseModel):
    id: int
    platform: PublishPlatform
    purpose: str
    display_name: str
    api_base: Optional[str] = None
    client_id: Optional[str] = None
    webhook_url: Optional[str] = None
    status: str
    is_active: bool
    notes: str = ""
    has_client_secret: bool = False
    has_access_token: bool = False
    has_refresh_token: bool = False


class PublishPrepareRequest(BaseModel):
    video_task_id: int
    platform: str
    platform_account_id: Optional[int] = None
    account_name: Optional[str] = None
    title: str
    hashtags: str = ""
    caption: str = ""
    scheduled_at: Optional[str] = None


class VideoTaskPublishPrepareRequest(BaseModel):
    platform: str = "douyin"
    platform_account_id: Optional[int] = None
    account_name: Optional[str] = None
    title: Optional[str] = None
    hashtags: str = ""
    caption: str = ""
    scheduled_at: Optional[str] = None


class PublishRecordUpdate(BaseModel):
    platform: Optional[str] = None
    platform_account_id: Optional[int] = None
    account_name: Optional[str] = None
    title: Optional[str] = None
    hashtags: Optional[str] = None
    caption: Optional[str] = None
    scheduled_at: Optional[str] = None
    publish_status: Optional[str] = None
    published_at: Optional[str] = None
