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


class Material(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    kind: MaterialKind
    copyright_status: CopyrightStatus = CopyrightStatus.owned
    file_path: Optional[str] = None
    source_url: Optional[str] = None
    tags: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


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
    duration_seconds: int = 30
    hook: str
    voiceover: str
    storyboard: str
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
    default_voice: Optional[str] = None
    authorization_scope: str = "internal_marketing"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class VideoTask(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    script_id: int
    digital_human_id: Optional[int] = None
    status: TaskStatus = TaskStatus.draft
    output_path: Optional[str] = None
    error_message: Optional[str] = None
    audit_notes: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PublishRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    video_task_id: int
    platform: str
    account_name: Optional[str] = None
    title: str
    publish_status: str = "prepared"
    published_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
