from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class DramaProject(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    premise: str = ""
    visual_style: str = ""
    episode_number: int = 1
    narrator_human_id: Optional[int] = None
    latest_video_task_id: Optional[int] = None
    status: str = "draft"
    owner_user_id: Optional[int] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class DramaCharacter(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(index=True)
    name: str
    role: str = ""
    visual_prompt: str = ""
    costume_prompt: str = ""
    voice_human_id: Optional[int] = None
    reference_material_id: Optional[int] = None
    owner_user_id: Optional[int] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DramaScene(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(index=True)
    name: str
    visual_prompt: str = ""
    reference_material_id: Optional[int] = None
    owner_user_id: Optional[int] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DramaShot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(index=True)
    scene_id: Optional[int] = None
    order_index: int = 1
    duration_seconds: int = 5
    beat: str = ""
    dialogue: str = ""
    visual_prompt: str = ""
    character_ids_json: str = "[]"
    reference_material_id: Optional[int] = None
    status: str = "draft"
    owner_user_id: Optional[int] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
