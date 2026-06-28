from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel


class MaterialKind(str, Enum):
    video = "video"
    image = "image"
    product = "product"
    portrait = "portrait"
    avatar_source = "avatar_source"
    reference = "reference"


class CopyrightStatus(str, Enum):
    owned = "owned"
    licensed = "licensed"
    reference_only = "reference_only"
    blocked = "blocked"


class TaskStatus(str, Enum):
    draft = "draft"
    queued = "queued"
    running = "running"
    needs_review = "needs_review"
    approved = "approved"
    rejected = "rejected"
    failed = "failed"


class UserRole(str, Enum):
    admin = "admin"
    operator = "operator"
    reviewer = "reviewer"


class TrendingSource(str, Enum):
    douyin = "douyin"
    wechat_channels = "wechat_channels"
    xiaohongshu = "xiaohongshu"
    kuaishou = "kuaishou"
    manual = "manual"


class PublishPlatform(str, Enum):
    douyin = "douyin"
    wechat_channels = "wechat_channels"
    xiaohongshu = "xiaohongshu"
    kuaishou = "kuaishou"
    volcengine = "volcengine"
    aliyun = "aliyun"
    manual = "manual"


class Material(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    kind: MaterialKind
    copyright_status: CopyrightStatus = CopyrightStatus.owned
    file_path: Optional[str] = None
    source_url: Optional[str] = None
    tags: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    password_hash: str
    role: UserRole = UserRole.admin
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AuthSession(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int
    token: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AIModelConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    provider: str
    purpose: str = "script"
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    model_name: str
    is_active: bool = False
    notes: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AIModelUsage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    model_config_id: Optional[int] = None
    provider: str
    purpose: str = "script"
    model_name: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    status: str = "success"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SystemSetting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str = ""
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TrendingSearch(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    platform: TrendingSource
    keyword: str
    category: Optional[str] = None
    limit: int = 20
    min_like_count: int = 0
    min_comment_count: int = 0
    sort_by: str = "engagement"
    status: TaskStatus = TaskStatus.queued
    result_count: int = 0
    notes: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TrendingVideo(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    search_id: Optional[int] = None
    platform: TrendingSource
    title: str
    source_url: str
    author: Optional[str] = None
    play_count: Optional[int] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    share_count: Optional[int] = None
    duration_seconds: Optional[int] = None
    hook: str = ""
    summary: str = ""
    tags: str = ""
    compliance_notes: str = "仅作为选题和结构参考，不可直接搬运画面或文案。"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TranscriptionTask(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    material_id: int
    provider: str = "mock"
    status: TaskStatus = TaskStatus.queued
    language: str = "zh-CN"
    transcript: str = ""
    summary: str = ""
    hook_analysis: str = ""
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ReferenceVideoAnalysis(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    material_id: int = Field(index=True)
    provider: str = "local"
    status: TaskStatus = TaskStatus.queued
    language: str = "zh-CN"
    duration_seconds: float = 0
    width: int = 0
    height: int = 0
    fps: float = 0
    has_audio: bool = False
    scene_count: int = 0
    avg_shot_seconds: float = 0
    visual_change_frequency: str = ""
    contact_sheet_path: Optional[str] = None
    dense_contact_sheet_path: Optional[str] = None
    timeline_json: str = ""
    transcript: str = ""
    script_analysis: str = ""
    shooting_analysis: str = ""
    editing_analysis: str = ""
    reusable_template: str = ""
    reuse_notes: str = ""
    quality_score: float = 0
    quality_summary: str = ""
    model_enhanced: bool = False
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Topic(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    industry: Optional[str] = None
    product_line: Optional[str] = None
    audience: Optional[str] = None
    reference_material_id: Optional[int] = None
    notes: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Script(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    topic_id: Optional[int] = None
    target_platform: str = "douyin"
    duration_seconds: int = 30
    hook: str
    voiceover: str
    storyboard: str
    storyboard_plan: str = ""
    seedance_prompt: str
    title_options: str
    hashtags: str
    compliance_notes: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DigitalHuman(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    role: Optional[str] = None
    style: str = "business"
    portrait_material_id: Optional[int] = None
    source_video_material_id: Optional[int] = None
    default_voice: Optional[str] = None
    authorization_scope: str = "internal_marketing"
    volcengine_auth_status: str = "not_started"
    volcengine_auth_url: Optional[str] = None
    volcengine_byted_token: Optional[str] = None
    volcengine_auth_result_code: Optional[str] = None
    volcengine_asset_group_id: Optional[str] = None
    volcengine_asset_group_uri: Optional[str] = None
    volcengine_asset_uri: Optional[str] = None
    volcengine_asset_status: Optional[str] = None
    volcengine_auth_payload: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class VideoTask(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    script_id: int
    digital_human_id: Optional[int] = None
    status: TaskStatus = TaskStatus.draft
    target_platform: str = "douyin"
    export_profile: str = "douyin_vertical"
    export_width: int = 1080
    export_height: int = 1920
    generation_mode: str = "short"
    production_mode: str = "talking_head_template"
    segment_count: int = 1
    completed_segments: int = 0
    subtitle_enabled: bool = True
    subtitle_style: str = "auto"
    subtitle_status: str = "pending"
    subtitle_srt_path: Optional[str] = None
    subtitle_ass_path: Optional[str] = None
    captioned_output_path: Optional[str] = None
    output_path: Optional[str] = None
    error_message: Optional[str] = None
    audit_notes: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class VideoSegment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    video_task_id: int = Field(index=True)
    segment_index: int
    title: str = ""
    duration_seconds: int = 10
    prompt: str = ""
    material_id: Optional[int] = None
    material_match_notes: str = ""
    status: TaskStatus = TaskStatus.queued
    output_path: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PlatformAccount(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    platform: PublishPlatform
    account_name: str
    owner: Optional[str] = None
    status: str = "active"
    is_default: bool = False
    notes: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PlatformCredential(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
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
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PublishRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    video_task_id: int
    platform: str
    platform_account_id: Optional[int] = None
    account_name: Optional[str] = None
    title: str
    hashtags: str = ""
    caption: str = ""
    scheduled_at: Optional[datetime] = None
    publish_status: str = "prepared"
    published_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
