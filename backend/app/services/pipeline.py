from __future__ import annotations

from datetime import datetime
from sqlmodel import select
from sqlmodel import Session
from app.models.entities import AIModelConfig, DigitalHuman, Material, Script, TaskStatus, VideoTask
from app.services.ai_clients import MediaGenerationClient


class VideoPipeline:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.media = MediaGenerationClient(self._active_video_model())

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
            human = self.session.get(DigitalHuman, task.digital_human_id) if task.digital_human_id else None
            portrait = self._portrait_path(human)
            source_video = self._source_video_path(human)
            voice = await self._voice_for_human(human, source_video, task)
            audio = await self.media.synthesize_voice(script.voiceover, voice)
            avatar = await self.media.generate_talking_avatar(portrait, audio, source_video)
            clips = await self.media.generate_seedance_clips(script.seedance_prompt)
            task.output_path = await self.media.compose_final_video(clips, avatar)
            task.status = TaskStatus.needs_review
            task.updated_at = datetime.utcnow()
            self.session.add(task)
            self.session.commit()
            self.session.refresh(task)
            return task
        except Exception as exc:
            task.status = TaskStatus.failed
            task.error_message = str(exc)
            task.updated_at = datetime.utcnow()
            self.session.add(task)
            self.session.commit()
            self.session.refresh(task)
            return task

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
                self._active_voice_clone_model(),
            )
        except Exception as exc:
            note = f"声音复刻未执行，继续使用默认语音：{exc}"
            task.audit_notes = f"{task.audit_notes}\n{note}".strip()
            self.session.add(task)
            self.session.commit()
            return None
        human.default_voice = voice_id
        self.session.add(human)
        self.session.commit()
        return voice_id

    def _active_video_model(self) -> AIModelConfig | None:
        return self.session.exec(
            select(AIModelConfig).where(
                AIModelConfig.purpose == "video",
                AIModelConfig.is_active == True,
            )
        ).first()

    def _active_voice_clone_model(self) -> AIModelConfig | None:
        return self.session.exec(
            select(AIModelConfig).where(
                AIModelConfig.purpose == "voice_clone",
                AIModelConfig.is_active == True,
            )
        ).first()
