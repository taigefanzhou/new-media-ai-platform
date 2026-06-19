from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field
from app.models.entities import CopyrightStatus, MaterialKind


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


class PublishPrepareRequest(BaseModel):
    video_task_id: int
    platform: str
    account_name: Optional[str] = None
    title: str
