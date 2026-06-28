from __future__ import annotations

from urllib.parse import urlparse

from sqlmodel import Session, select

from app.models.entities import AIModelConfig


LOCAL_PROVIDERS = {"local", "mock", "stub"}
LOCAL_HTTP_PROVIDERS = {
    "comfyui",
    "cosyvoice",
    "cosyvoice-clone",
    "f5-tts",
    "fish-speech",
    "http-json",
    "openvoice",
    "sadtalker",
    "vllm",
    "whisperx",
}


PURPOSE_PROVIDER_SCORES = {
    "script": {
        "volcengine-ark": 90,
        "volcengine-ark-lite": 78,
        "volcengine-ark-mini": 64,
        "aliyun-bailian": 72,
        "aliyun-bailian-latest": 70,
        "aliyun-bailian-max": 68,
        "deepseek": 60,
    },
    "video": {
        "seedance": 95,
        "seedance-fast": 88,
        "seedance-mini": 76,
        "volcengine-seedance": 95,
        "comfyui": 45,
        "wan": 35,
    },
    "digital_human": {
        "aliyun-wan-s2v": 95,
        "d-id": 65,
        "did": 65,
        "volcengine-digital-human": 55,
        "heygen": 50,
        "sadtalker": 30,
    },
    "tts": {
        "aliyun-cosyvoice": 95,
        "aliyun-tts": 88,
        "volcengine-tts": 70,
        "cosyvoice": 45,
        "fish-speech": 42,
    },
    "voice_clone": {
        "aliyun-cosyvoice-clone": 95,
        "volcengine-voice-clone": 70,
        "cosyvoice-clone": 45,
        "openvoice": 40,
        "f5-tts": 38,
    },
    "asr": {
        "aliyun-bailian": 90,
        "volcengine": 72,
        "whisperx": 45,
    },
    "video_understanding": {
        "volcengine-ark": 90,
        "aliyun-bailian": 75,
    },
    "compliance": {
        "volcengine-ark": 88,
        "aliyun-bailian": 76,
    },
    "knowledge": {
        "aliyun-bailian": 88,
        "volcengine-ark": 76,
    },
}


def api_base_looks_valid(api_base: str | None) -> bool:
    if not api_base:
        return False
    parsed = urlparse(api_base)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def model_requires_api_base(purpose: str, provider: str) -> bool:
    provider = (provider or "").strip().lower()
    if provider in LOCAL_PROVIDERS:
        return False
    return True


def model_requires_api_key(purpose: str, provider: str) -> bool:
    provider = (provider or "").strip().lower()
    if provider in LOCAL_PROVIDERS or provider in LOCAL_HTTP_PROVIDERS:
        return False
    if purpose == "video" and provider == "comfyui":
        return False
    return True


def is_model_config_ready(config: AIModelConfig | None) -> bool:
    if config is None:
        return False
    provider = (config.provider or "").strip().lower()
    if model_requires_api_base(config.purpose, provider) and not api_base_looks_valid(config.api_base):
        return False
    if model_requires_api_key(config.purpose, provider) and not config.api_key:
        return False
    return True


def _scenario_score(config: AIModelConfig, scenario: str = "") -> int:
    provider = (config.provider or "").strip().lower()
    model_name = (config.model_name or "").strip().lower()
    scenario = (scenario or "").strip().lower()
    score = PURPOSE_PROVIDER_SCORES.get(config.purpose, {}).get(provider, 40)

    if scenario in {"digital_human", "talking_head_template", "voice_preview"}:
        if config.purpose == "digital_human" and "wan" in provider and "s2v" in model_name:
            score += 20
        if config.purpose == "tts" and "cosyvoice" in provider:
            score += 15
    if scenario in {"seedance_scene", "b_roll", "mixed_video"} and config.purpose == "video":
        if "seedance" in provider or "seedance" in model_name:
            score += 20
    if scenario in {"long_script", "script_generation"} and config.purpose == "script":
        if "seed" in model_name or "pro" in model_name:
            score += 12
        if "mini" in provider or "mini" in model_name:
            score -= 18
    if scenario in {"cost_saving", "preview"}:
        if "mini" in provider or "mini" in model_name:
            score += 18
        if "lite" in model_name or "flash" in model_name:
            score += 10
        if provider in LOCAL_HTTP_PROVIDERS:
            score += 6
    return score


def choose_model_config(session: Session, purpose: str, scenario: str = "") -> AIModelConfig | None:
    configs = list(session.exec(select(AIModelConfig).where(AIModelConfig.purpose == purpose)).all())
    ready_configs = [config for config in configs if is_model_config_ready(config)]
    if not ready_configs:
        return next((config for config in configs if config.is_active), None)

    def score(config: AIModelConfig) -> tuple[int, int, int]:
        return (
            _scenario_score(config, scenario) + (100 if config.is_active else 0),
            1 if config.is_active else 0,
            config.id or 0,
        )

    return max(ready_configs, key=score)


def model_choice_note(purpose: str, config: AIModelConfig | None, scenario: str = "") -> str:
    label = {
        "script": "脚本",
        "video": "视频镜头",
        "tts": "口播试听/配音",
        "voice_clone": "声音复刻",
        "digital_human": "数字人",
        "asr": "转写",
        "video_understanding": "视频理解",
        "compliance": "合规检查",
        "knowledge": "知识库",
    }.get(purpose, purpose)
    if config is None:
        return f"{label}模型：未找到可用配置。"
    scenario_text = f"，场景：{scenario}" if scenario else ""
    return f"{label}模型：系统智能选择 {config.name}（{config.provider} / {config.model_name}{scenario_text}）。"
