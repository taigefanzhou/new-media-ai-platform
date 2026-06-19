from __future__ import annotations

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "New Media AI Platform"
    database_url: str = "sqlite:///./data/platform.db"
    storage_dir: str = "./data/storage"
    admin_username: str = "admin"
    admin_password: str = "admin123456"

    llm_provider: str = "stub"
    llm_api_base: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model: str = "qwen3-or-deepseek"

    tts_provider: str = "mock"
    tts_api_base: Optional[str] = None
    tts_api_key: Optional[str] = None
    tts_voice: str = "default"

    seedance_api_base: Optional[str] = None
    seedance_api_key: Optional[str] = None
    seedance_model: str = "seedance"
    comfyui_api_base: Optional[str] = None
    video_generation_provider: str = "mock"

    digital_human_provider: str = "sadtalker"
    digital_human_api_base: Optional[str] = None
    digital_human_api_key: Optional[str] = None

    composition_provider: str = "mock"
    ffmpeg_binary: str = "ffmpeg"

    trending_search_provider: str = "mock"
    trending_search_api_base: Optional[str] = None
    trending_search_api_key: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
