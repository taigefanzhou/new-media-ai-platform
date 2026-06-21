from __future__ import annotations

from datetime import datetime
import re
from sqlmodel import select
from sqlmodel import Session
from app.core.config import get_settings
from app.core.storage import get_storage_root
from app.models.entities import AIModelConfig, DigitalHuman, Material, Script, TaskStatus, VideoSegment, VideoTask
from app.services.ai_clients import MediaGenerationClient
from app.services.export_profiles import resolve_export_profile
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
            profile = resolve_export_profile(task.export_profile, task.target_platform or script.target_platform)
            task.target_platform = task.target_platform or script.target_platform or profile.platform
            task.export_profile = profile.key
            task.export_width = profile.width
            task.export_height = profile.height
            segment_specs = self.media.segment_plan(
                script.seedance_prompt,
                script.storyboard,
                script.duration_seconds,
                script.storyboard_plan,
            )
            segments = self._reset_segments(task, segment_specs)
            task.generation_mode = "long" if script.duration_seconds >= 120 else "short"
            task.segment_count = len(segments)
            task.completed_segments = 0
            task.audit_notes = self._task_plan_notes(task, script)
            self.session.add(task)
            self.session.commit()
            self.session.refresh(task)

            human = self.session.get(DigitalHuman, task.digital_human_id) if task.digital_human_id else None
            portrait_material = self._portrait_material(human)
            portrait = portrait_material.file_path if portrait_material else None
            portrait_url = portrait_material.source_url if portrait_material else None
            source_video_material = self._source_video_material(human)
            source_video = source_video_material.file_path if source_video_material else None
            source_video_url = source_video_material.source_url if source_video_material else None
            voice = await self._voice_for_human(human, source_video, task, source_video_url)
            if task.production_mode == "talking_head_template":
                if human is None:
                    raise RuntimeError("数字人口播模板需要选择数字人。")
                if not any([portrait, portrait_url, source_video, source_video_url]):
                    raise RuntimeError("数字人口播模板需要数字人头像或口播源视频素材。")
                if not self.media.can_generate_talking_avatar():
                    raise RuntimeError("数字人口播模板需要先配置真实数字人驱动接口，不能使用头像或图文预览代替。")
                avatar, audio = await self._generate_talking_avatar_for_script(
                    script,
                    voice,
                    portrait,
                    source_video,
                    task,
                    portrait_url=portrait_url,
                    source_video_url=source_video_url,
                )
                task.output_path = await self.media.compose_talking_head_template(
                    avatar,
                    script.voiceover,
                    script.storyboard_plan,
                    title=self._script_title(script),
                    speaker_name=self._speaker_name(human),
                    speaker_role=self._speaker_role(human),
                    duration_seconds=script.duration_seconds,
                    audio_path=audio,
                    export_profile=task.export_profile,
                )
                for segment in segments:
                    segment.status = TaskStatus.needs_review
                    segment.output_path = task.output_path
                    segment.updated_at = datetime.utcnow()
                    self.session.add(segment)
                task.completed_segments = len(segments)
                task.status = TaskStatus.needs_review
                task.updated_at = datetime.utcnow()
                self.session.add(task)
                self.session.commit()
                self.session.refresh(task)
                return task
            if task.production_mode == "seedance_scene":
                audio = await self._synthesize_voice(script, voice)
                clips = []
                for segment in segments:
                    clip_path = await self._run_segment(segment, task)
                    clips.append(clip_path)
                task.output_path = await self.media.compose_scene_video(clips, audio, export_profile=task.export_profile)
                task.status = TaskStatus.needs_review
                task.updated_at = datetime.utcnow()
                self.session.add(task)
                self.session.commit()
                self.session.refresh(task)
                return task
            if task.production_mode == "dynamic_explainer":
                audio = await self._synthesize_voice(script, voice)
                task.output_path = await self.media.compose_dynamic_explainer(
                    script.voiceover,
                    script.storyboard_plan,
                    audio,
                    portrait,
                    duration_seconds=script.duration_seconds,
                    export_profile=task.export_profile,
                )
                for segment in segments:
                    segment.status = TaskStatus.needs_review
                    segment.output_path = task.output_path
                    segment.updated_at = datetime.utcnow()
                    self.session.add(segment)
                task.completed_segments = len(segments)
                task.status = TaskStatus.needs_review
                task.updated_at = datetime.utcnow()
                self.session.add(task)
                self.session.commit()
                self.session.refresh(task)
                return task
            if task.production_mode == "digital_human" and not self.media.can_generate_talking_avatar():
                raise RuntimeError("真人数字人口播需要先配置真实数字人驱动接口。")
            avatar, _audio = await self._generate_talking_avatar_for_script(
                script,
                voice,
                portrait,
                source_video,
                task,
                portrait_url=portrait_url,
                source_video_url=source_video_url,
            )
            clips = []
            for segment in segments:
                clip_path = await self._run_segment(segment, task)
                clips.append(clip_path)
            task.output_path = await self.media.compose_final_video(clips, avatar, export_profile=task.export_profile)
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
                task.export_profile,
            )
            self._record_usage(
                "video",
                self.video_model_config,
                provider=self._usage_provider(self.video_model_config, self.settings.video_generation_provider),
                model_name=self._usage_model(self.video_model_config, self.settings.seedance_model),
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
                provider=self._usage_provider(self.video_model_config, self.settings.video_generation_provider),
                model_name=self._usage_model(self.video_model_config, self.settings.seedance_model),
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
        profile = resolve_export_profile(task.export_profile, task.target_platform)
        plan_note = (
            f"成片方式：{task.production_mode}。长视频分段计划：脚本时长 {script.duration_seconds} 秒，"
            f"共 {task.segment_count} 段，每段约 10 秒，可用于后续分段预览和失败段重跑。"
            f"导出规格：{profile.label}，{profile.width}x{profile.height}，{profile.notes}"
        )
        return f"{base_note}\n{plan_note}".strip() if base_note else plan_note

    def _script_title(self, script: Script) -> str:
        for line in script.title_options.splitlines():
            title = line.strip()
            if title:
                return title
        return script.hook

    def _speaker_role(self, human: DigitalHuman) -> str:
        role = (human.role or "").strip()
        if role:
            return role
        return "品牌顾问｜企业方案讲解｜数字人口播"

    def _speaker_name(self, human: DigitalHuman) -> str:
        name = (human.name or "").strip()
        for candidate in ("李明亮", "梁欣欣"):
            if candidate in name:
                return candidate
        return name[:8] if len(name) > 8 else name or "数字人"

    def _portrait_material(self, human: DigitalHuman | None) -> Material | None:
        if human is None or human.portrait_material_id is None:
            return None
        return self.session.get(Material, human.portrait_material_id)

    def _portrait_path(self, human: DigitalHuman | None) -> str | None:
        material = self._portrait_material(human)
        return material.file_path if material else None

    def _source_video_path(self, human: DigitalHuman | None) -> str | None:
        material = self._source_video_material(human)
        if material is None:
            return None
        return material.file_path

    def _source_video_material(self, human: DigitalHuman | None) -> Material | None:
        if human is None or human.source_video_material_id is None:
            return None
        return self.session.get(Material, human.source_video_material_id)

    async def _voice_for_human(
        self,
        human: DigitalHuman | None,
        source_video_path: str | None,
        task: VideoTask,
        source_video_url: str | None = None,
    ) -> str | None:
        if human is None:
            return None
        if human.default_voice:
            return human.default_voice
        if not source_video_path and not source_video_url:
            return None
        try:
            voice_id = await self.media.clone_voice_from_source_video(
                source_video_path or source_video_url or "",
                human.name,
                self.voice_clone_model_config,
                source_url=source_video_url,
            )
            self._record_usage(
                "voice_clone",
                self.voice_clone_model_config,
                provider=self._usage_provider(self.voice_clone_model_config, self.settings.voice_clone_provider),
                model_name=self._usage_model(self.voice_clone_model_config, self.settings.voice_clone_provider),
            )
        except Exception as exc:
            self._record_usage(
                "voice_clone",
                self.voice_clone_model_config,
                provider=self._usage_provider(self.voice_clone_model_config, self.settings.voice_clone_provider),
                model_name=self._usage_model(self.voice_clone_model_config, self.settings.voice_clone_provider),
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
        return await self._synthesize_text_voice(script.voiceover, voice)

    async def _synthesize_text_voice(self, text: str, voice: str | None) -> str:
        try:
            audio = await self.media.synthesize_voice(text, voice)
            self._record_usage(
                "tts",
                self.tts_model_config,
                provider=self._usage_provider(self.tts_model_config, self.settings.tts_provider),
                model_name=self._usage_model(self.tts_model_config, self.settings.tts_voice),
                prompt_tokens=estimate_text_tokens(text),
            )
            return audio
        except Exception:
            self._record_usage(
                "tts",
                self.tts_model_config,
                provider=self._usage_provider(self.tts_model_config, self.settings.tts_provider),
                model_name=self._usage_model(self.tts_model_config, self.settings.tts_voice),
                prompt_tokens=estimate_text_tokens(text),
                status="failed",
            )
            raise

    async def _generate_talking_avatar_for_script(
        self,
        script: Script,
        voice: str | None,
        portrait_path: str | None,
        source_video_path: str | None,
        task: VideoTask,
        portrait_url: str | None = None,
        source_video_url: str | None = None,
    ) -> tuple[str, str | None]:
        chunks = self._voiceover_chunks(script.voiceover)
        if self._should_split_talking_avatar_audio(script) and len(chunks) > 1:
            avatars: list[str] = []
            for index, chunk in enumerate(chunks):
                audio = await self._synthesize_text_voice(chunk, voice)
                avatars.append(
                    await self._generate_talking_avatar(
                        portrait_path,
                        audio,
                        source_video_path,
                        f"{script.seedance_prompt}\nTalking-head section {index + 1}/{len(chunks)}.",
                        portrait_url=portrait_url,
                        source_video_url=source_video_url,
                    )
                )
            avatar = await self.media.compose_talking_avatar_sequence(avatars)
            note = f"数字人口播已自动拆成 {len(chunks)} 段短音频生成，再合成为一条完整口播。"
            task.audit_notes = f"{task.audit_notes}\n{note}".strip()
            self.session.add(task)
            self.session.commit()
            return avatar, None

        audio = await self._synthesize_voice(script, voice)
        avatar = await self._generate_talking_avatar(
            portrait_path,
            audio,
            source_video_path,
            script.seedance_prompt,
            portrait_url=portrait_url,
            source_video_url=source_video_url,
        )
        return avatar, audio

    def _should_split_talking_avatar_audio(self, script: Script) -> bool:
        config = self.digital_human_model_config
        provider = (config.provider if config else self.settings.digital_human_provider or "").lower()
        model_name = (config.model_name if config else self.settings.digital_human_provider or "").lower()
        value = f"{provider} {model_name}"
        return "wan" in value and "s2v" in value

    def _voiceover_chunks(self, text: str, max_chars: int = 46) -> list[str]:
        cleaned = re.sub(r"\s+", " ", (text or "").strip())
        if not cleaned:
            return []
        sentences = [item.strip() for item in re.split(r"(?<=[。！？!?；;，,])", cleaned) if item.strip()]
        chunks: list[str] = []
        current = ""
        for sentence in sentences or [cleaned]:
            if len(sentence) > max_chars:
                if current:
                    chunks.append(current.strip())
                    current = ""
                chunks.extend(sentence[i : i + max_chars].strip() for i in range(0, len(sentence), max_chars))
                continue
            candidate = f"{current}{sentence}" if current else sentence
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    chunks.append(current.strip())
                current = sentence
        if current:
            chunks.append(current.strip())
        return [chunk for chunk in chunks if chunk]

    async def _generate_talking_avatar(
        self,
        portrait_path: str | None,
        audio_path: str,
        source_video_path: str | None,
        style_prompt: str = "",
        portrait_url: str | None = None,
        source_video_url: str | None = None,
    ) -> str:
        try:
            avatar = await self.media.generate_talking_avatar(
                portrait_path,
                audio_path,
                source_video_path,
                style_prompt,
                portrait_url=portrait_url,
                source_video_url=source_video_url,
            )
            self._record_usage(
                "digital_human",
                self.digital_human_model_config,
                provider=self._usage_provider(self.digital_human_model_config, self.settings.digital_human_provider),
                model_name=self._usage_model(self.digital_human_model_config, self.settings.digital_human_provider),
            )
            return avatar
        except Exception:
            self._record_usage(
                "digital_human",
                self.digital_human_model_config,
                provider=self._usage_provider(self.digital_human_model_config, self.settings.digital_human_provider),
                model_name=self._usage_model(self.digital_human_model_config, self.settings.digital_human_provider),
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

    def _usage_provider(self, config: AIModelConfig | None, fallback: str) -> str:
        return config.provider if config and config.provider else fallback

    def _usage_model(self, config: AIModelConfig | None, fallback: str) -> str:
        return config.model_name if config and config.model_name else fallback
