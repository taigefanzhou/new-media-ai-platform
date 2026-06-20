from __future__ import annotations

from typing import Any, Optional

from sqlmodel import Session

from app.models.entities import AIModelConfig, AIModelUsage


def estimate_text_tokens(*parts: object) -> int:
    text = "\n".join(str(part or "") for part in parts)
    return max(1, len(text) // 2) if text.strip() else 0


def record_model_usage(
    session: Session,
    purpose: str,
    model_config: Optional[AIModelConfig] = None,
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    status: str = "success",
) -> AIModelUsage:
    prompt_tokens = _safe_int(prompt_tokens)
    completion_tokens = _safe_int(completion_tokens)
    total_tokens = _safe_int(total_tokens)
    if total_tokens <= 0:
        total_tokens = prompt_tokens + completion_tokens

    usage = AIModelUsage(
        model_config_id=model_config.id if model_config else None,
        provider=model_config.provider if model_config else provider or "unknown",
        purpose=purpose,
        model_name=model_config.model_name if model_config else model_name or "unknown",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        status=status,
    )
    session.add(usage)
    return usage


def record_generated_model_usage(
    session: Session,
    purpose: str,
    generated: Any,
    model_config: Optional[AIModelConfig] = None,
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    status: str = "success",
) -> AIModelUsage:
    prompt_tokens = _safe_int(getattr(generated, "prompt_tokens", 0))
    completion_tokens = _safe_int(getattr(generated, "completion_tokens", 0))
    total_tokens = _safe_int(getattr(generated, "total_tokens", 0))
    if total_tokens <= 0:
        completion_tokens = completion_tokens or estimate_generated_tokens(generated)
        total_tokens = prompt_tokens + completion_tokens

    return record_model_usage(
        session=session,
        purpose=purpose,
        model_config=model_config,
        provider=provider,
        model_name=model_name,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        status=status,
    )


def estimate_generated_tokens(generated: Any) -> int:
    fields = (
        "hook",
        "voiceover",
        "storyboard",
        "seedance_prompt",
        "title_options",
        "hashtags",
        "compliance_notes",
    )
    return estimate_text_tokens(*(getattr(generated, field, "") for field in fields))


def _safe_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
