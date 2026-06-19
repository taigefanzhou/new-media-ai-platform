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
            audio = await self.media.synthesize_voice(script.voiceover, human.default_voice if human else None)
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

    def _active_video_model(self) -> AIModelConfig | None:
        return self.session.exec(
            select(AIModelConfig).where(
                AIModelConfig.purpose == "video",
                AIModelConfig.is_active == True,
            )
        ).first()
