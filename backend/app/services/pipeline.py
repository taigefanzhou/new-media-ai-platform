from __future__ import annotations

from datetime import datetime
from sqlmodel import Session
from app.models.entities import Script, TaskStatus, VideoTask
from app.services.ai_clients import MediaGenerationClient


class VideoPipeline:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.media = MediaGenerationClient()

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
            audio = await self.media.synthesize_voice(script.voiceover)
            avatar = await self.media.generate_talking_avatar(None, audio)
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
