from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field
from app.models.entities import CopyrightStatus, MaterialKind, PublishPlatform, TrendingSource


class LoginRequest(BaseModel):
    username: str
    password: str


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


class TrendingSearchCreate(BaseModel):
    platform: TrendingSource
    keyword: str
    category: Optional[str] = None
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


class MaterialCreate(BaseModel):
    name: str
    kind: MaterialKind
    copyright_status: CopyrightStatus = CopyrightStatus.owned
    source_url: Optional[str] = None
    tags: str = ""


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
    duration_seconds: int = 30
    target_platform: str = "douyin"


class DigitalHumanCreate(BaseModel):
    name: str
    role: Optional[str] = None
    style: str = "business"
    portrait_material_id: Optional[int] = None
    default_voice: Optional[str] = None
    authorization_scope: str = "internal_marketing"


class VideoTaskCreate(BaseModel):
    script_id: int
    digital_human_id: Optional[int] = None


class ScriptVideoTaskCreate(BaseModel):
    digital_human_id: Optional[int] = None


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
