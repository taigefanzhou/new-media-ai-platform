from __future__ import annotations

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "New Media AI Platform"
    database_url: str = "sqlite:///./data/platform.db"
    storage_dir: str = "./data/storage"

    llm_provider: str = "stub"
    llm_api_base: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model: str = "qwen3-or-deepseek"

    seedance_api_base: Optional[str] = None
    seedance_api_key: Optional[str] = None
    comfyui_api_base: Optional[str] = None
    cosyvoice_api_base: Optional[str] = None
    digital_human_provider: str = "sadtalker"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
