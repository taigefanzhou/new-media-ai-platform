from __future__ import annotations

from datetime import datetime
import json
import mimetypes
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from fastapi import Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.api.access import _assign_owner, _ensure_record_access, _owned_statement, _require_write_user
from app.api.material_support import _save_uploaded_material
from app.api.system_models import _smart_model_config
from app.api.system_storage import upload_material_to_remote
from app.core.auth import current_user
from app.core.config import get_settings
from app.core.db import get_session
from app.core.storage import get_storage_root
from app.models.entities import (
    AIModelConfig,
    CopyrightStatus,
    DigitalHuman,
    Material,
    MaterialKind,
    PlatformCredential,
    ReferenceVideoAnalysis,
    Script,
    TaskStatus,
    Topic,
    TranscriptionTask,
    User,
)
from app.schemas.requests import (
    MaterialCreate,
    ReferenceMaterialLinkCreate,
    ReferenceVideoAnalysisCreate,
    ScriptGenerateRequest,
    TranscriptionTaskCreate,
)
from app.services.ai_clients import ScriptGenerator
from app.services.asr import ASRClient
from app.services.link_resolver import (
    LinkResolverCredential,
    LinkResolution,
    ShortVideoLinkResolver,
    detect_short_video_platform,
)
from app.services.usage import estimate_text_tokens, record_generated_model_usage, record_model_usage
from app.services.video_analysis import ReferenceVideoAnalyzer


REFERENCE_MEDIA_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".m4v",
    ".webm",
    ".mkv",
    ".avi",
    ".mp3",
    ".m4a",
    ".aac",
    ".wav",
}


def _delete_local_file(path_value: str | None) -> None:
    if not path_value or path_value.startswith("mock://") or path_value.startswith("http"):
        return
    path = Path(path_value)
    if path.exists() and path.is_file():
        path.unlink()
    parent = path.parent
    try:
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
    except OSError:
        return


def _url_preview(value: str | None, max_length: int = 110) -> str:
    if not value:
        return ""
    if len(value) <= max_length:
        return value
    return f"{value[:max_length]}..."


async def _probe_reference_media_url(source_url: str) -> dict[str, object]:
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return {"ok": False, "content_type": "", "message": "不是有效的视频地址。"}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        ),
        "Accept": "video/mp4,video/*;q=0.9,audio/*;q=0.8,*/*;q=0.5",
        "Range": "bytes=0-1023",
    }
    try:
        async with httpx.AsyncClient(timeout=25, follow_redirects=True, headers=headers) as client:
            async with client.stream("GET", source_url) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                content_disposition = response.headers.get("content-disposition", "")
                looks_like_media = _response_looks_like_reference_media(
                    str(response.url),
                    content_type,
                    content_disposition,
                )
                return {
                    "ok": bool(looks_like_media),
                    "content_type": content_type,
                    "final_url_preview": _url_preview(str(response.url)),
                    "message": "已确认可访问视频文件。" if looks_like_media else "解析地址可访问，但不像视频或音频文件。",
                }
    except Exception as exc:
        return {"ok": False, "content_type": "", "message": f"视频地址访问失败：{exc}"}


def _reference_title_from_url(source_url: str) -> str:
    parsed = urlparse(source_url)
    filename = Path(parsed.path).name
    stem = Path(filename).stem if filename else ""
    if stem and stem.lower() not in {"stodownload", "download", "video"}:
        return stem[:80]
    return parsed.netloc or "参考视频链接"


def _reference_tags(platform: str, tags: str, *extra_tags: str) -> str:
    values = ["参考素材", platform.strip()]
    values.extend(item.strip() for item in tags.split(",") if item.strip())
    values.extend(item.strip() for item in extra_tags if item and item.strip())
    deduped = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return ",".join(deduped)


def _merge_reference_tags(existing_tags: str, platform: str, resolver_name: str, parse_status: str) -> str:
    retained = [
        item.strip()
        for item in existing_tags.split(",")
        if item.strip()
        and not item.strip().startswith("解析:")
        and item.strip() not in {"已下载视频", "需上传源文件", "仅保存链接"}
    ]
    return _reference_tags(platform, ",".join(retained), f"解析:{resolver_name}", parse_status)


def _media_suffix_from_response(source_url: str, content_type: str, content_disposition: str) -> str:
    disposition_parts = content_disposition.split(";") if content_disposition else []
    for part in disposition_parts:
        if "filename=" not in part:
            continue
        filename = part.split("=", 1)[1].strip().strip('"')
        suffix = Path(filename).suffix.lower()
        if suffix in REFERENCE_MEDIA_EXTENSIONS:
            return suffix

    parsed_url = urlparse(source_url)
    url_suffix = Path(parsed_url.path).suffix.lower()
    if url_suffix in REFERENCE_MEDIA_EXTENSIONS:
        return url_suffix
    if "finder.video.qq.com" in parsed_url.netloc and "stodownload" in parsed_url.path:
        return ".mp4"

    normalized_type = content_type.split(";", 1)[0].strip().lower()
    if normalized_type == "video/mp4":
        return ".mp4"
    if normalized_type == "video/quicktime":
        return ".mov"
    if normalized_type == "audio/mpeg":
        return ".mp3"
    if normalized_type == "audio/mp4":
        return ".m4a"
    guessed = mimetypes.guess_extension(normalized_type) or ""
    if guessed in REFERENCE_MEDIA_EXTENSIONS:
        return guessed
    if normalized_type.startswith("video/"):
        return ".mp4"
    if normalized_type.startswith("audio/"):
        return ".m4a"
    return ""


def _response_looks_like_reference_media(source_url: str, content_type: str, content_disposition: str) -> bool:
    normalized_type = content_type.split(";", 1)[0].strip().lower()
    if normalized_type.startswith(("video/", "audio/")):
        return True
    if _media_suffix_from_response(source_url, content_type, content_disposition):
        return True
    return False


async def _download_reference_media(source_url: str, storage_dir: Path) -> Path | None:
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="请输入有效的视频链接。")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        ),
        "Accept": "video/mp4,video/*;q=0.9,audio/*;q=0.8,*/*;q=0.5",
    }
    max_bytes = 800 * 1024 * 1024
    async with httpx.AsyncClient(timeout=600, follow_redirects=True, headers=headers) as client:
        async with client.stream("GET", source_url) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            content_disposition = response.headers.get("content-disposition", "")
            if not _response_looks_like_reference_media(source_url, content_type, content_disposition):
                return None
            suffix = _media_suffix_from_response(source_url, content_type, content_disposition) or ".mp4"
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > max_bytes:
                raise HTTPException(status_code=400, detail="参考视频文件超过 800MB，请先下载后上传。")

            storage_dir.mkdir(parents=True, exist_ok=True)
            file_path = storage_dir / f"source{suffix}"
            total = 0
            with open(file_path, "wb") as output:
                async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        output.close()
                        _delete_local_file(str(file_path))
                        raise HTTPException(status_code=400, detail="参考视频文件超过 800MB，请先下载后上传。")
                    output.write(chunk)
            if total == 0:
                _delete_local_file(str(file_path))
                return None
            return file_path


def _link_resolver_credentials(session: Session, platform: str) -> list[LinkResolverCredential]:
    credentials = session.exec(
        select(PlatformCredential).where(
            PlatformCredential.purpose == "link_resolver",
            PlatformCredential.is_active == True,  # noqa: E712
        )
    ).all()
    allowed_platforms = {platform, "manual"}
    result = []
    for credential in credentials:
        credential_platform = (
            credential.platform.value if hasattr(credential.platform, "value") else str(credential.platform)
        )
        if credential_platform not in allowed_platforms:
            continue
        if not credential.api_base:
            continue
        result.append(
            LinkResolverCredential(
                platform=credential_platform,
                display_name=credential.display_name,
                api_base=credential.api_base,
                client_id=credential.client_id or "",
                client_secret=credential.client_secret or "",
                access_token=credential.access_token or "",
                notes=credential.notes or "",
            )
        )
    return result


async def _resolve_and_download_reference_media(
    source_url: str,
    platform_name: str,
    storage_dir: Path,
    session: Session,
) -> tuple[Path | None, LinkResolution | None]:
    file_path: Path | None = None
    resolution: LinkResolution | None = None
    try:
        file_path = await _download_reference_media(source_url, storage_dir)
    except HTTPException:
        raise
    except Exception:
        file_path = None
    if file_path:
        return file_path, resolution

    try:
        resolver = ShortVideoLinkResolver()
        resolution = await resolver.resolve(
            source_url,
            platform_name,
            _link_resolver_credentials(session, platform_name),
        )
        if resolution.media_url and resolution.media_url != source_url:
            file_path = await _download_reference_media(resolution.media_url, storage_dir)
    except HTTPException:
        raise
    except Exception:
        file_path = None
    return file_path, resolution


def _topic_title_from_text(text: str) -> str:
    cleaned = " ".join(text.replace("\n", " ").split())
    if not cleaned:
        return "参考视频改写选题"
    return cleaned[:48]


def list_materials(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[Material]:
    statement = _owned_statement(select(Material).order_by(Material.created_at.desc()), Material, user)
    return list(session.exec(statement).all())


def create_material(
    payload: MaterialCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> Material:
    _require_write_user(user)
    material = Material.model_validate(payload)
    _assign_owner(material, user)
    session.add(material)
    session.commit()
    session.refresh(material)
    return material


def preview_material(
    material_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> FileResponse:
    material = session.get(Material, material_id)
    _ensure_record_access(material, user, "Material")
    if not material.file_path:
        raise HTTPException(status_code=404, detail="Material preview not found")
    path = Path(material.file_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Material file not found")
    return FileResponse(path)


def delete_material(
    material_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict[str, object]:
    material = session.get(Material, material_id)
    _ensure_record_access(material, user, "Material", write=True)

    humans = session.exec(
        select(DigitalHuman).where(
            (DigitalHuman.portrait_material_id == material_id)
            | (DigitalHuman.source_video_material_id == material_id)
        )
    ).all()
    for human in humans:
        if human.portrait_material_id == material_id:
            human.portrait_material_id = None
        if human.source_video_material_id == material_id:
            human.source_video_material_id = None
        session.add(human)

    topics = session.exec(select(Topic).where(Topic.reference_material_id == material_id)).all()
    for topic in topics:
        topic.reference_material_id = None
        session.add(topic)

    transcriptions = session.exec(select(TranscriptionTask).where(TranscriptionTask.material_id == material_id)).all()
    for task in transcriptions:
        session.delete(task)
    analyses = session.exec(select(ReferenceVideoAnalysis).where(ReferenceVideoAnalysis.material_id == material_id)).all()
    for analysis in analyses:
        _delete_local_file(analysis.contact_sheet_path)
        _delete_local_file(analysis.dense_contact_sheet_path)
        session.delete(analysis)

    _delete_local_file(material.file_path)
    session.delete(material)
    session.commit()
    return {"deleted": True, "id": material_id}


async def create_reference_material_from_link(
    payload: ReferenceMaterialLinkCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> Material:
    _require_write_user(user)
    source_url = payload.source_url.strip()
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="请输入 http 或 https 开头的视频链接。")

    platform_name = detect_short_video_platform(source_url, payload.platform)
    storage_dir = get_storage_root(session) / "materials" / uuid4().hex
    file_path: Path | None = None
    resolution: LinkResolution | None = None
    if payload.download:
        file_path, resolution = await _resolve_and_download_reference_media(
            source_url,
            platform_name,
            storage_dir,
            session,
        )

    resolver_name = resolution.resolver_name if resolution else ("direct-download" if file_path else "link-only")
    title = (payload.title or "").strip() or (resolution.title if resolution else "") or _reference_title_from_url(source_url)
    parse_status = "已下载视频" if file_path else ("需上传源文件" if payload.download else "仅保存链接")
    material = Material(
        name=title,
        kind=MaterialKind.reference,
        copyright_status=CopyrightStatus.reference_only,
        file_path=str(file_path) if file_path else None,
        source_url=source_url,
        tags=_reference_tags(platform_name, payload.tags, f"解析:{resolver_name}", parse_status),
    )
    _assign_owner(material, user)
    session.add(material)
    session.commit()
    session.refresh(material)
    return material


async def resolve_download_reference_material(
    material_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> Material:
    material = session.get(Material, material_id)
    _ensure_record_access(material, user, "Material", write=True)
    if material.kind != MaterialKind.reference or not material.source_url:
        raise HTTPException(status_code=400, detail="只有通过链接保存的参考素材可以解析下载。")
    if material.file_path and Path(material.file_path).exists():
        return material

    source_url = material.source_url.strip()
    platform_name = detect_short_video_platform(source_url, "auto")
    storage_dir = get_storage_root(session) / "materials" / uuid4().hex
    file_path, resolution = await _resolve_and_download_reference_media(
        source_url,
        platform_name,
        storage_dir,
        session,
    )
    resolver_name = resolution.resolver_name if resolution else ("direct-download" if file_path else "link-only")
    parse_status = "已下载视频" if file_path else "需上传源文件"
    if file_path:
        material.file_path = str(file_path)
    if resolution and resolution.title and material.name == _reference_title_from_url(source_url):
        material.name = resolution.title[:120]
    material.tags = _merge_reference_tags(material.tags, platform_name, resolver_name, parse_status)
    session.add(material)
    session.commit()
    session.refresh(material)
    return material


async def upload_material(
    file: UploadFile = File(...),
    name: Optional[str] = Form(default=None),
    kind: MaterialKind = Form(default=MaterialKind.image),
    copyright_status: CopyrightStatus = Form(default=CopyrightStatus.owned),
    tags: str = Form(default=""),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> Material:
    _require_write_user(user)
    return await _save_uploaded_material(
        file=file,
        kind=kind,
        name=name,
        copyright_status=copyright_status,
        tags=tags,
        session=session,
        owner=user,
    )


def create_transcription_task(
    payload: TranscriptionTaskCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> TranscriptionTask:
    _require_write_user(user)
    material = session.get(Material, payload.material_id)
    _ensure_record_access(material, user, "Material")
    task = TranscriptionTask(
        material_id=payload.material_id,
        language=payload.language,
        provider=get_settings().asr_provider,
        status=TaskStatus.queued,
    )
    _assign_owner(task, user)
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


async def run_transcription_task(
    task_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> TranscriptionTask:
    task = session.get(TranscriptionTask, task_id)
    _ensure_record_access(task, user, "Transcription task", write=True)
    material = session.get(Material, task.material_id)
    _ensure_record_access(material, user, "Material")
    active_model = _smart_model_config(session, "asr", "transcription")
    settings = get_settings()
    task.provider = active_model.provider if active_model else settings.asr_provider
    task.status = TaskStatus.running
    session.add(task)
    session.commit()
    try:
        result = await ASRClient(active_model).transcribe(task, material)
        task.transcript = result.transcript
        task.summary = result.summary
        task.hook_analysis = result.hook_analysis
        task.status = TaskStatus.needs_review
        record_model_usage(
            session=session,
            purpose="asr",
            model_config=active_model,
            provider=active_model.provider if active_model else settings.asr_provider,
            model_name=active_model.model_name if active_model else settings.asr_model,
            completion_tokens=estimate_text_tokens(result.transcript, result.summary, result.hook_analysis),
        )
    except Exception as exc:
        task.status = TaskStatus.failed
        task.error_message = str(exc)
        record_model_usage(
            session=session,
            purpose="asr",
            model_config=active_model,
            provider=active_model.provider if active_model else settings.asr_provider,
            model_name=active_model.model_name if active_model else settings.asr_model,
            status="failed",
        )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def list_transcription_tasks(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[TranscriptionTask]:
    statement = _owned_statement(
        select(TranscriptionTask).order_by(TranscriptionTask.created_at.desc()),
        TranscriptionTask,
        user,
    )
    return list(session.exec(statement).all())


def create_topic_from_transcription(
    task_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> Topic:
    task = session.get(TranscriptionTask, task_id)
    _ensure_record_access(task, user, "Transcription task", write=True)
    if not task.transcript:
        raise HTTPException(status_code=400, detail="Transcription has no transcript")
    material = session.get(Material, task.material_id)
    title_seed = task.hook_analysis or task.summary or task.transcript[:80]
    topic = Topic(
        title=_topic_title_from_text(title_seed),
        industry="待补充",
        audience="目标客户",
        reference_material_id=task.material_id,
        notes=(
            f"来源素材：{material.name if material else task.material_id}\n"
            f"摘要：{task.summary}\n"
            f"钩子分析：{task.hook_analysis}"
        ),
    )
    _assign_owner(topic, user)
    session.add(topic)
    session.commit()
    session.refresh(topic)
    return topic


async def generate_script_from_transcription(
    task_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> Script:
    task = session.get(TranscriptionTask, task_id)
    _ensure_record_access(task, user, "Transcription task", write=True)
    if not task.transcript:
        raise HTTPException(status_code=400, detail="Transcription has no transcript")
    topic = (
        "基于参考视频结构，生成原创公司短视频脚本。"
        f"参考摘要：{task.summary}。"
        f"开头钩子分析：{task.hook_analysis}。"
        "要求只借鉴结构和选题，不复制原文。"
    )
    active_model = _smart_model_config(session, "script", "script_generation")
    generated = await ScriptGenerator(active_model).generate(
        topic=topic,
        brand_voice="专业、可信、原创、适合公司数字人口播",
        duration_seconds=30,
        target_platform="douyin",
    )
    script = Script(
        topic_id=None,
        target_platform="douyin",
        duration_seconds=30,
        hook=generated.hook,
        voiceover=generated.voiceover,
        storyboard=generated.storyboard,
        storyboard_plan=json.dumps(getattr(generated, "storyboard_plan", []) or [], ensure_ascii=False),
        seedance_prompt=generated.seedance_prompt,
        title_options=generated.title_options,
        hashtags=generated.hashtags,
        compliance_notes=f"{generated.compliance_notes}\n基于转写任务 #{task.id} 生成，仅借鉴结构，不搬运原文。",
    )
    _assign_owner(script, user)
    session.add(script)
    record_generated_model_usage(
        session,
        "script",
        generated,
        active_model,
        provider=active_model.provider if active_model else get_settings().llm_provider,
        model_name=active_model.model_name if active_model else get_settings().llm_model,
    )
    session.commit()
    session.refresh(script)
    return script


def _latest_transcript_for_material(session: Session, material_id: int) -> str:
    task = session.exec(
        select(TranscriptionTask)
        .where(TranscriptionTask.material_id == material_id, TranscriptionTask.transcript != "")
        .order_by(TranscriptionTask.updated_at.desc())
    ).first()
    return task.transcript if task else ""


def create_reference_video_analysis(
    payload: ReferenceVideoAnalysisCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> ReferenceVideoAnalysis:
    _require_write_user(user)
    material = session.get(Material, payload.material_id)
    _ensure_record_access(material, user, "Material")
    if material.kind not in (MaterialKind.avatar_source, MaterialKind.video, MaterialKind.reference):
        raise HTTPException(status_code=400, detail="深度视频拆解需要选择视频或参考素材。")
    task = ReferenceVideoAnalysis(
        material_id=payload.material_id,
        provider=payload.provider,
        language=payload.language,
        status=TaskStatus.queued,
    )
    _assign_owner(task, user)
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


async def run_reference_video_analysis(
    analysis_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> ReferenceVideoAnalysis:
    task = session.get(ReferenceVideoAnalysis, analysis_id)
    _ensure_record_access(task, user, "Reference video analysis")
    material = session.get(Material, task.material_id)
    _ensure_record_access(material, user, "Material")

    active_model = _smart_model_config(session, "video_understanding", "reference_analysis")
    task.provider = active_model.provider if active_model else task.provider or "local"
    task.status = TaskStatus.running
    task.error_message = None
    task.updated_at = datetime.utcnow()
    session.add(task)
    session.commit()
    session.refresh(task)

    try:
        transcript = _latest_transcript_for_material(session, task.material_id)
        result = await ReferenceVideoAnalyzer(active_model).analyze(task, material, transcript=transcript)
        task.duration_seconds = result.duration_seconds
        task.width = result.width
        task.height = result.height
        task.fps = result.fps
        task.has_audio = result.has_audio
        task.scene_count = result.scene_count
        task.avg_shot_seconds = result.avg_shot_seconds
        task.visual_change_frequency = result.visual_change_frequency
        task.contact_sheet_path = result.contact_sheet_path
        task.dense_contact_sheet_path = result.dense_contact_sheet_path
        task.timeline_json = result.timeline_json
        task.transcript = transcript
        task.script_analysis = result.script_analysis
        task.shooting_analysis = result.shooting_analysis
        task.editing_analysis = result.editing_analysis
        task.reusable_template = result.reusable_template
        task.reuse_notes = result.reuse_notes
        task.quality_score = result.quality_score
        task.quality_summary = result.quality_summary
        task.model_enhanced = result.model_enhanced
        task.status = TaskStatus.needs_review
        estimated_completion_tokens = estimate_text_tokens(
            task.script_analysis,
            task.shooting_analysis,
            task.editing_analysis,
            task.reusable_template,
            task.reuse_notes,
        )
        completion_tokens = result.completion_tokens or max(0, result.total_tokens - result.prompt_tokens)
        record_model_usage(
            session=session,
            purpose="video_understanding",
            model_config=active_model,
            provider=task.provider,
            model_name=active_model.model_name if active_model else "local-video-analyzer",
            prompt_tokens=result.prompt_tokens,
            completion_tokens=completion_tokens or estimated_completion_tokens,
        )
    except Exception as exc:
        task.status = TaskStatus.failed
        task.error_message = str(exc)
        record_model_usage(
            session=session,
            purpose="video_understanding",
            model_config=active_model,
            provider=task.provider,
            model_name=active_model.model_name if active_model else "local-video-analyzer",
            status="failed",
        )
    task.updated_at = datetime.utcnow()
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def list_reference_video_analyses(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[ReferenceVideoAnalysis]:
    statement = _owned_statement(
        select(ReferenceVideoAnalysis).order_by(ReferenceVideoAnalysis.created_at.desc()),
        ReferenceVideoAnalysis,
        user,
    )
    return list(session.exec(statement).all())


def approve_reference_video_analysis(
    analysis_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> ReferenceVideoAnalysis:
    task = session.get(ReferenceVideoAnalysis, analysis_id)
    _ensure_record_access(task, user, "Reference video analysis")
    if task.status == TaskStatus.failed:
        raise HTTPException(status_code=400, detail="失败的拆解结果不能采纳，请重新拆解。")
    task.status = TaskStatus.approved
    task.updated_at = datetime.utcnow()
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def reject_reference_video_analysis(
    analysis_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> ReferenceVideoAnalysis:
    task = session.get(ReferenceVideoAnalysis, analysis_id)
    _ensure_record_access(task, user, "Reference video analysis", write=True)
    task.status = TaskStatus.rejected
    task.updated_at = datetime.utcnow()
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def reference_video_analysis_contact_sheet(
    analysis_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> FileResponse:
    task = session.get(ReferenceVideoAnalysis, analysis_id)
    _ensure_record_access(task, user, "Reference video analysis")
    if not task.contact_sheet_path:
        raise HTTPException(status_code=404, detail="Contact sheet not found")
    path = Path(task.contact_sheet_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Contact sheet file not found")
    return FileResponse(path, media_type="image/jpeg")


def reference_video_analysis_dense_contact_sheet(
    analysis_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> FileResponse:
    task = session.get(ReferenceVideoAnalysis, analysis_id)
    _ensure_record_access(task, user, "Reference video analysis")
    if not task.dense_contact_sheet_path:
        raise HTTPException(status_code=404, detail="Dense contact sheet not found")
    path = Path(task.dense_contact_sheet_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Dense contact sheet file not found")
    return FileResponse(path, media_type="image/jpeg")


def _create_reference_script_record(
    session: Session,
    payload: ScriptGenerateRequest,
    generated,
    model_config: AIModelConfig | None,
    owner: User,
) -> Script:
    script = Script(
        topic_id=payload.topic_id,
        target_platform=payload.target_platform,
        duration_seconds=payload.duration_seconds,
        hook=generated.hook,
        voiceover=generated.voiceover,
        storyboard=generated.storyboard,
        storyboard_plan=json.dumps(getattr(generated, "storyboard_plan", []) or [], ensure_ascii=False),
        seedance_prompt=generated.seedance_prompt,
        title_options=generated.title_options,
        hashtags=generated.hashtags,
        compliance_notes=generated.compliance_notes,
    )
    _assign_owner(script, owner)
    session.add(script)
    record_generated_model_usage(
        session,
        "script",
        generated,
        model_config,
        provider=model_config.provider if model_config else get_settings().llm_provider,
        model_name=model_config.model_name if model_config else get_settings().llm_model,
    )
    session.commit()
    session.refresh(script)
    return script


async def generate_script_from_reference_video_analysis(
    analysis_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> Script:
    task = session.get(ReferenceVideoAnalysis, analysis_id)
    _ensure_record_access(task, user, "Reference video analysis", write=True)
    if task.status != TaskStatus.approved:
        raise HTTPException(status_code=400, detail="请先在拆解详情里采纳这个参考模板。")
    material = session.get(Material, task.material_id)
    topic = (
        "基于参考视频的结构生成原创公司短视频脚本，不能复刻原画面、原文和人物。"
        f"参考素材：{material.name if material else task.material_id}。"
        f"脚本结构分析：{task.script_analysis}\n"
        f"拍摄方式分析：{task.shooting_analysis}\n"
        f"剪辑方式分析：{task.editing_analysis}\n"
        f"可复用模板：{task.reusable_template}\n"
        "请改写成适合酒店智能化、酒店运营或公司负责人数字人口播的原创脚本。"
    )
    active_model = _smart_model_config(session, "script", "script_generation")
    generated = await ScriptGenerator(active_model).generate(
        topic=topic,
        brand_voice="专业、可信、适合公司负责人口播；学习参考视频的结构和节奏，但不搬运原文和画面。",
        duration_seconds=max(30, min(180, int(task.duration_seconds or 60))),
        target_platform="wechat_channels" if task.height >= task.width else "douyin",
        output_language="zh-CN",
    )
    payload = ScriptGenerateRequest(
        topic=topic,
        brand_voice="专业、可信、适合公司负责人口播；学习参考视频的结构和节奏，但不搬运原文和画面。",
        duration_seconds=max(30, min(180, int(task.duration_seconds or 60))),
        target_platform="wechat_channels" if task.height >= task.width else "douyin",
        output_language="zh-CN",
    )
    script = _create_reference_script_record(session, payload, generated, active_model, owner=user)
    script.compliance_notes = (
        f"{script.compliance_notes}\n基于深度视频拆解 #{task.id} 生成，仅学习结构、节奏、拍摄和剪辑方法。"
    )
    session.add(script)
    session.commit()
    session.refresh(script)
    return script
