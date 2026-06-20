from __future__ import annotations

from datetime import datetime
from sqlmodel import select
from sqlmodel import Session
from app.core.config import get_settings
from app.core.storage import get_storage_root
from app.models.entities import AIModelConfig, DigitalHuman, Material, Script, TaskStatus, VideoSegment, VideoTask
from app.services.ai_clients import MediaGenerationClient
from app.services.usage import estimate_text_tokens, record_model_usage


class VideoPipeline:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()
        self.video_model_config = self._active_model("video")
        self.tts_model_config = self._active_model("tts")
        self.digital_human_model_config = self._active_model("digital_human")
        self.voice_clone_model_config = self._active_model("voice_clone")
        self.media = MediaGenerationClient(
            self.video_model_config,
            self.tts_model_config,
            self.digital_human_model_config,
            storage_dir=get_storage_root(session),
        )

    async def run(self, task: VideoTask) -> VideoTask:
        task.status = TaskStatus.running
        task.updated_at = datetime.utcnow()
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)

        script = self.session.get(Script, task.script_id)
        if script is None:
            task.status = TaskStatus.failed
            task.error_message = "Script not found"
            self.session.add(task)
            self.session.commit()
            return task

        try:
            segment_specs = self.media.segment_plan(script.seedance_prompt, script.storyboard, script.duration_seconds)
            segments = self._reset_segments(task, segment_specs)
            task.generation_mode = "long" if script.duration_seconds >= 120 else "short"
            task.segment_count = len(segments)
            task.completed_segments = 0
            task.audit_notes = self._task_plan_notes(task, script)
            self.session.add(task)
            self.session.commit()
            self.session.refresh(task)

            human = self.session.get(DigitalHuman, task.digital_human_id) if task.digital_human_id else None
            portrait = self._portrait_path(human)
            source_video = self._source_video_path(human)
            voice = await self._voice_for_human(human, source_video, task)
            audio = await self._synthesize_voice(script, voice)
            avatar = await self._generate_talking_avatar(portrait, audio, source_video)
            clips = []
            for segment in segments:
                clip_path = await self._run_segment(segment, task)
                clips.append(clip_path)
            task.output_path = await self.media.compose_final_video(clips, avatar)
            task.status = TaskStatus.needs_review
            task.updated_at = datetime.utcnow()
            self.session.add(task)
            self.session.commit()
            self.session.refresh(task)
            return task
        except Exception as exc:
            task.status = TaskStatus.failed
            task.error_message = task.error_message or str(exc)
            task.updated_at = datetime.utcnow()
            self.session.add(task)
            self.session.commit()
            self.session.refresh(task)
            return task

    def _reset_segments(self, task: VideoTask, segment_specs: list[dict[str, object]]) -> list[VideoSegment]:
        existing = self.session.exec(select(VideoSegment).where(VideoSegment.video_task_id == task.id)).all()
        for segment in existing:
            self.session.delete(segment)
        self.session.commit()

        segments: list[VideoSegment] = []
        for index, spec in enumerate(segment_specs):
            segment = VideoSegment(
                video_task_id=task.id or 0,
                segment_index=index + 1,
                title=str(spec.get("title") or f"第 {index + 1} 段"),
                duration_seconds=int(spec.get("duration_seconds") or 10),
                prompt=str(spec.get("prompt") or ""),
                status=TaskStatus.queued,
            )
            self.session.add(segment)
            segments.append(segment)
        self.session.commit()
        for segment in segments:
            self.session.refresh(segment)
        return segments

    async def _run_segment(self, segment: VideoSegment, task: VideoTask) -> str:
        segment.status = TaskStatus.running
        segment.updated_at = datetime.utcnow()
        self.session.add(segment)
        self.session.commit()
        try:
            clip_path = await self.media.generate_video_segment(
                segment.prompt,
                segment.duration_seconds,
                segment.segment_index - 1,
                task.segment_count,
            )
            self._record_usage(
                "video",
                self.video_model_config,
                provider=self.settings.video_generation_provider,
                model_name=self.settings.seedance_model,
                prompt_tokens=estimate_text_tokens(segment.prompt),
            )
            segment.output_path = clip_path
            segment.status = TaskStatus.needs_review
            segment.updated_at = datetime.utcnow()
            task.completed_segments = min(task.segment_count, task.completed_segments + 1)
            task.updated_at = datetime.utcnow()
            self.session.add(segment)
            self.session.add(task)
            self.session.commit()
            return clip_path
        except Exception as exc:
            self._record_usage(
                "video",
                self.video_model_config,
                provider=self.settings.video_generation_provider,
                model_name=self.settings.seedance_model,
                prompt_tokens=estimate_text_tokens(segment.prompt),
                status="failed",
            )
            segment.status = TaskStatus.failed
            segment.error_message = str(exc)
            segment.updated_at = datetime.utcnow()
            task.status = TaskStatus.failed
            task.error_message = f"第 {segment.segment_index} 段生成失败：{exc}"
            task.updated_at = datetime.utcnow()
            self.session.add(segment)
            self.session.add(task)
            self.session.commit()
            raise

    def _task_plan_notes(self, task: VideoTask, script: Script) -> str:
        base_note = task.audit_notes.strip()
        plan_note = (
            f"长视频分段计划：脚本时长 {script.duration_seconds} 秒，"
            f"共 {task.segment_count} 段，每段约 10 秒，可用于后续分段预览和失败段重跑。"
        )
        return f"{base_note}\n{plan_note}".strip() if base_note else plan_note

    def _portrait_path(self, human: DigitalHuman | None) -> str | None:
        if human is None or human.portrait_material_id is None:
            return None
        material = self.session.get(Material, human.portrait_material_id)
        if material is None:
            return None
        return material.file_path

    def _source_video_path(self, human: DigitalHuman | None) -> str | None:
        if human is None or human.source_video_material_id is None:
            return None
        material = self.session.get(Material, human.source_video_material_id)
        if material is None:
            return None
        return material.file_path

    async def _voice_for_human(
        self,
        human: DigitalHuman | None,
        source_video_path: str | None,
        task: VideoTask,
    ) -> str | None:
        if human is None:
            return None
        if human.default_voice:
            return human.default_voice
        if not source_video_path:
            return None
        try:
            voice_id = await self.media.clone_voice_from_source_video(
                source_video_path,
                human.name,
                self.voice_clone_model_config,
            )
            self._record_usage(
                "voice_clone",
                self.voice_clone_model_config,
                provider=self.settings.voice_clone_provider,
                model_name=self.settings.voice_clone_provider,
            )
        except Exception as exc:
            self._record_usage(
                "voice_clone",
                self.voice_clone_model_config,
                provider=self.settings.voice_clone_provider,
                model_name=self.settings.voice_clone_provider,
                status="failed",
            )
            note = f"声音复刻未执行，继续使用默认语音：{exc}"
            task.audit_notes = f"{task.audit_notes}\n{note}".strip()
            self.session.add(task)
            self.session.commit()
            return None
        human.default_voice = voice_id
        self.session.add(human)
        self.session.commit()
        return voice_id

    async def _synthesize_voice(self, script: Script, voice: str | None) -> str:
        try:
            audio = await self.media.synthesize_voice(script.voiceover, voice)
            self._record_usage(
                "tts",
                self.tts_model_config,
                provider=self.settings.tts_provider,
                model_name=self.settings.tts_voice,
                prompt_tokens=estimate_text_tokens(script.voiceover),
            )
            return audio
        except Exception:
            self._record_usage(
                "tts",
                self.tts_model_config,
                provider=self.settings.tts_provider,
                model_name=self.settings.tts_voice,
                prompt_tokens=estimate_text_tokens(script.voiceover),
                status="failed",
            )
            raise

    async def _generate_talking_avatar(
        self,
        portrait_path: str | None,
        audio_path: str,
        source_video_path: str | None,
    ) -> str:
        try:
            avatar = await self.media.generate_talking_avatar(portrait_path, audio_path, source_video_path)
            self._record_usage(
                "digital_human",
                self.digital_human_model_config,
                provider=self.settings.digital_human_provider,
                model_name=self.settings.digital_human_provider,
            )
            return avatar
        except Exception:
            self._record_usage(
                "digital_human",
                self.digital_human_model_config,
                provider=self.settings.digital_human_provider,
                model_name=self.settings.digital_human_provider,
                status="failed",
            )
            raise

    def _active_model(self, purpose: str) -> AIModelConfig | None:
        return self.session.exec(
            select(AIModelConfig).where(
                AIModelConfig.purpose == purpose,
                AIModelConfig.is_active == True,
            )
        ).first()

    def _record_usage(
        self,
        purpose: str,
        model_config: AIModelConfig | None,
        provider: str,
        model_name: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        status: str = "success",
    ) -> None:
        record_model_usage(
            session=self.session,
            purpose=purpose,
            model_config=model_config,
            provider=provider,
            model_name=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            status=status,
        )
