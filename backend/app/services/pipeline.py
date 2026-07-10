from __future__ import annotations

from datetime import datetime
import re
from sqlmodel import select
from sqlmodel import Session
from app.core.config import get_settings
from app.core.storage import get_storage_root
from app.models.entities import (
    AIModelConfig,
    CopyrightStatus,
    DigitalHuman,
    Material,
    MaterialKind,
    PlatformCredential,
    Script,
    TaskStatus,
    VideoSegment,
    VideoTask,
)
from app.services.ai_clients import MediaGenerationClient
from app.services.export_profiles import resolve_export_profile
from app.services.model_router import choose_model_config, model_choice_note
from app.services.professional_render import ProfessionalRenderClient
from app.services.subtitles import SubtitleEngine
from app.services.video_analysis import ReferenceVideoAnalyzer
from app.services.video_quality import GeneratedVideoQualityGuard, VideoQualityResult
from app.services.usage import estimate_text_tokens, record_model_usage
from app.services.video_skills import material_selection_rules, quality_guard_checklist, video_skill_manifest


class VideoPipeline:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()
        self.video_model_config = choose_model_config(session, "video", "seedance_scene")
        self.tts_model_config = choose_model_config(session, "tts", "voice_preview")
        self.digital_human_model_config = choose_model_config(session, "digital_human", "talking_head_template")
        self.digital_human_platform_credential = self._active_platform_credential("volcengine", "digital_human")
        self.voice_clone_model_config = choose_model_config(session, "voice_clone", "digital_human")
        self.quality_model_config = choose_model_config(session, "video_understanding", "quality_review")
        self.quality_guard = GeneratedVideoQualityGuard()
        self.media = MediaGenerationClient(
            self.video_model_config,
            self.tts_model_config,
            self.digital_human_model_config,
            self.digital_human_platform_credential,
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
            self._configure_models_for_task(task, script)
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
                return await self._finalize_task(task, script)
            if task.production_mode == "seedance_scene":
                audio = await self._synthesize_voice(script, voice)
                clips = []
                for segment in segments:
                    clip_path = await self._run_segment(segment, task)
                    clips.append(clip_path)
                task.output_path = await self.media.compose_scene_video(clips, audio, export_profile=task.export_profile)
                return await self._finalize_task(task, script)
            if task.production_mode == "material_mix":
                audio = await self._synthesize_voice(script, voice)
                clips = []
                for segment in segments:
                    clip_path = await self._run_segment(segment, task)
                    clips.append(clip_path)
                task.output_path = await self.media.compose_scene_video(clips, audio, export_profile=task.export_profile)
                return await self._finalize_task(task, script)
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
                return await self._finalize_task(task, script)
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
            return await self._finalize_task(task, script)
        except Exception as exc:
            task.status = TaskStatus.failed
            task.error_message = task.error_message or str(exc)
            task.updated_at = datetime.utcnow()
            self.session.add(task)
            self.session.commit()
            self.session.refresh(task)
            return task

    async def _finalize_task(self, task: VideoTask, script: Script) -> VideoTask:
        await self._apply_professional_render(task, script)
        if task.subtitle_enabled:
            task.subtitle_status = "running"
            self.session.add(task)
            self.session.commit()
            self.session.refresh(task)
            try:
                SubtitleEngine().render_for_task(task, script)
            except Exception as exc:
                task.subtitle_status = "failed"
                task.audit_notes = f"{task.audit_notes}\n字幕引擎执行失败，已保留无字幕原片：{exc}".strip()
        else:
            task.subtitle_status = "disabled"
        await self._review_final_output(task, script)
        task.status = TaskStatus.needs_review
        task.updated_at = datetime.utcnow()
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return task

    async def resume_completed_segments(self, task: VideoTask) -> VideoTask:
        if task.production_mode not in {"seedance_scene", "material_mix"}:
            raise RuntimeError("当前成片方式不支持从分段恢复合成。")
        script = self.session.get(Script, task.script_id)
        if script is None:
            raise RuntimeError("找不到任务对应脚本。")
        segments = list(
            self.session.exec(
                select(VideoSegment)
                .where(VideoSegment.video_task_id == task.id)
                .order_by(VideoSegment.segment_index.asc())
            ).all()
        )
        if not segments or any(not segment.output_path for segment in segments):
            raise RuntimeError("分段视频尚未全部完成，无法恢复合成。")

        task.status = TaskStatus.running
        task.error_message = None
        task.completed_segments = len(segments)
        task.updated_at = datetime.utcnow()
        self.session.add(task)
        self.session.commit()

        voice = await self._synthesize_voice(script, None)
        task.output_path = await self.media.compose_scene_video(
            [segment.output_path for segment in segments if segment.output_path],
            voice,
            export_profile=task.export_profile,
        )
        return await self._finalize_task(task, script)

    async def _apply_professional_render(self, task: VideoTask, script: Script) -> None:
        original_output = task.output_path
        try:
            rendered = await ProfessionalRenderClient().render_task(task, script, original_output)
        except Exception as exc:
            task.audit_notes = f"{task.audit_notes}\n专业包装渲染失败，已保留基础成片：{exc}".strip()
            return
        if not rendered:
            return
        task.output_path = rendered
        task.audit_notes = f"{task.audit_notes}\n专业包装：已通过 Remotion 模板生成剪映式包装成片。".strip()

    def _reset_segments(self, task: VideoTask, segment_specs: list[dict[str, object]]) -> list[VideoSegment]:
        existing = self.session.exec(select(VideoSegment).where(VideoSegment.video_task_id == task.id)).all()
        for segment in existing:
            self.session.delete(segment)
        self.session.commit()

        segments: list[VideoSegment] = []
        for index, spec in enumerate(segment_specs):
            material, match_note = self._match_material_for_segment(spec, task.owner_user_id)
            segment = VideoSegment(
                video_task_id=task.id or 0,
                segment_index=index + 1,
                title=str(spec.get("title") or f"第 {index + 1} 段"),
                duration_seconds=int(spec.get("duration_seconds") or 10),
                prompt=str(spec.get("prompt") or ""),
                material_id=material.id if material else None,
                material_match_notes=match_note,
                status=TaskStatus.queued,
                quality_status="pending",
                quality_score=0,
                quality_summary="等待生成后自动质检。",
                generation_attempts=0,
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
            material = self.session.get(Material, segment.material_id) if segment.material_id else None
            if material and task.owner_user_id is not None and material.owner_user_id != task.owner_user_id:
                material = None
            uses_library_clip = bool(
                task.production_mode == "material_mix"
                and material
                and material.file_path
                and material.copyright_status in {CopyrightStatus.owned, CopyrightStatus.licensed}
            )
            if uses_library_clip:
                clip_path = await self.media.material_to_scene_clip(
                    material.file_path,
                    segment.duration_seconds,
                    task.export_profile,
                )
            else:
                clip_path = await self._generate_segment_candidate(segment, task, material)
            quality = self._inspect_segment_output(clip_path, segment, task)
            chosen_path = clip_path
            if quality.status in {"retry", "failed"} and not uses_library_clip:
                retry_path = await self._generate_segment_candidate(
                    segment,
                    task,
                    material,
                    repair_instruction=(
                        "Avoid blank or dark frames. Keep the requested duration and aspect ratio. "
                        "Use a clear, stable live-action shot."
                    ),
                )
                retry_quality = self._inspect_segment_output(retry_path, segment, task)
                if retry_quality.score > quality.score:
                    chosen_path = retry_path
                    quality = VideoQualityResult(
                        retry_quality.score,
                        "passed" if retry_quality.score >= 82 else "review",
                        f"自动重做后选中第 2 个候选：{retry_quality.summary}",
                        retry_quality.duration_seconds,
                        retry_quality.width,
                        retry_quality.height,
                    )
                else:
                    quality = VideoQualityResult(
                        quality.score,
                        "review",
                        f"自动重做未优于首版，保留第 1 个候选：{quality.summary}",
                        quality.duration_seconds,
                        quality.width,
                        quality.height,
                    )
            elif uses_library_clip:
                quality = VideoQualityResult(
                    quality.score,
                    "passed" if quality.score >= 82 else "review",
                    f"复用已授权素材：{quality.summary}",
                    quality.duration_seconds,
                    quality.width,
                    quality.height,
                )
            segment.output_path = chosen_path
            segment.status = TaskStatus.needs_review
            segment.quality_status = quality.status
            segment.quality_score = quality.score
            segment.quality_summary = quality.summary
            segment.updated_at = datetime.utcnow()
            task.completed_segments = min(task.segment_count, task.completed_segments + 1)
            task.updated_at = datetime.utcnow()
            self.session.add(segment)
            self.session.add(task)
            self.session.commit()
            return chosen_path
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

    async def _generate_segment_candidate(
        self,
        segment: VideoSegment,
        task: VideoTask,
        material: Material | None,
        repair_instruction: str = "",
    ) -> str:
        prompt = " ".join(part for part in (segment.prompt, repair_instruction) if part).strip()
        segment.generation_attempts += 1
        self.session.add(segment)
        self.session.commit()
        clip_path = await self.media.generate_video_segment(
            prompt,
            segment.duration_seconds,
            segment.segment_index - 1,
            task.segment_count,
            task.export_profile,
            reference_media=self._seedance_reference_media(material),
        )
        self._record_usage(
            "video",
            self.video_model_config,
            provider=self._usage_provider(self.video_model_config, self.settings.video_generation_provider),
            model_name=self._usage_model(self.video_model_config, self.settings.seedance_model),
            prompt_tokens=estimate_text_tokens(prompt),
        )
        return clip_path

    def _inspect_segment_output(self, clip_path: str, segment: VideoSegment, task: VideoTask) -> VideoQualityResult:
        return self.quality_guard.inspect(
            clip_path,
            expected_duration_seconds=segment.duration_seconds,
            expected_width=task.export_width,
            expected_height=task.export_height,
        )

    async def _review_final_output(self, task: VideoTask, script: Script) -> None:
        output_path = task.captioned_output_path or task.output_path
        if not output_path:
            task.quality_status = "failed"
            task.quality_score = 0
            task.quality_summary = "未找到成片文件。"
            return
        result = self.quality_guard.inspect(
            output_path,
            expected_duration_seconds=script.duration_seconds,
            expected_width=task.export_width,
            expected_height=task.export_height,
        )
        task.quality_status = result.status
        task.quality_score = result.score
        task.quality_summary = result.summary
        visual_review = await ReferenceVideoAnalyzer(self.quality_model_config).review_generated_output(
            output_path,
            script.seedance_prompt,
            script.duration_seconds,
        )
        if visual_review is not None:
            visual_score = float(visual_review["score"])
            task.quality_score = min(result.score, visual_score)
            task.quality_status = "passed" if task.quality_score >= 82 and visual_review["decision"] == "passed" else "review"
            task.quality_summary = f"{result.summary} 视觉复核：{visual_review['summary']}"
            usage = visual_review["usage"] if isinstance(visual_review["usage"], dict) else {}
            self._record_usage(
                "video_understanding",
                self.quality_model_config,
                provider=self._usage_provider(self.quality_model_config, "video-understanding"),
                model_name=self._usage_model(self.quality_model_config, "video-quality-review"),
                prompt_tokens=int(usage.get("prompt_tokens") or usage.get("promptTokenCount") or 0),
                completion_tokens=int(usage.get("completion_tokens") or usage.get("completionTokenCount") or 0),
            )
        task.audit_notes = (
            f"{task.audit_notes}\n自动成片质检：{task.quality_score:.0f} 分，{task.quality_summary}"
        ).strip()

    def _task_plan_notes(self, task: VideoTask, script: Script) -> str:
        base_note = task.audit_notes.strip()
        profile = resolve_export_profile(task.export_profile, task.target_platform)
        model_notes = [
            model_choice_note("tts", self.tts_model_config, "voice_preview"),
        ]
        if task.production_mode in {"material_mix", "seedance_scene", "digital_human"}:
            model_notes.append(model_choice_note("video", self.video_model_config, task.production_mode))
        if task.production_mode in {"talking_head_template", "digital_human"}:
            model_notes.append(model_choice_note("digital_human", self.digital_human_model_config, task.production_mode))
        plan_note = (
            f"成片方式：{task.production_mode}。长视频分段计划：脚本时长 {script.duration_seconds} 秒，"
            f"共 {task.segment_count} 段，每段约 10 秒，可用于后续分段预览和失败段重跑。"
            f"导出规格：{profile.label}，{profile.width}x{profile.height}，{profile.notes}"
            f"\n{chr(10).join(model_notes)}"
            f"\n内置视频生产 Skill：{self._skill_summary_note()}"
            f"\n素材匹配规则：{'; '.join(material_selection_rules()[:3])}"
            f"\n成片质检清单：{'; '.join(quality_guard_checklist())}"
        )
        return f"{base_note}\n{plan_note}".strip() if base_note else plan_note

    def _skill_summary_note(self) -> str:
        return " -> ".join(str(item["label"]) for item in video_skill_manifest())

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

    def _match_material_for_segment(
        self,
        spec: dict[str, object],
        owner_user_id: int | None = None,
    ) -> tuple[Material | None, str]:
        query = " ".join(
            str(spec.get(key) or "")
            for key in ("title", "visual", "prompt", "asset_or_background")
        ).lower()
        query_tokens = self._match_tokens(query)
        if not query_tokens:
            return None, "没有足够关键词，生成时将由 Seedance 补镜头。"
        statement = select(Material).where(
            Material.kind.in_([
                MaterialKind.video,
                MaterialKind.image,
                MaterialKind.product,
                MaterialKind.portrait,
                MaterialKind.reference,
                MaterialKind.avatar_source,
            ]),
            Material.copyright_status.in_([
                CopyrightStatus.owned,
                CopyrightStatus.licensed,
                CopyrightStatus.reference_only,
            ]),
        )
        if owner_user_id is not None:
            statement = statement.where(Material.owner_user_id == owner_user_id)
        candidates = self.session.exec(statement).all()
        best: tuple[int, Material] | None = None
        for material in candidates:
            text = f"{material.name} {material.tags} {material.kind}".lower()
            score = len(query_tokens & self._match_tokens(text))
            if material.kind == MaterialKind.product and any(token in query for token in ("产品", "方案", "系统", "dashboard", "screen")):
                score += 1
            if material.kind == MaterialKind.video and any(token in query for token in ("场景", "镜头", "实拍", "hotel", "room", "lobby")):
                score += 1
            if score > 0 and (best is None or score > best[0]):
                best = (score, material)
        if best is None:
            return None, "素材库暂无匹配素材，生成时将由 Seedance 补镜头。"
        material = best[1]
        copyright_note = "仅作模型参考，不直接混剪" if material.copyright_status == CopyrightStatus.reference_only else "可用于成片"
        return material, f"素材匹配 Skill 推荐素材 #{material.id}：{material.name}（{copyright_note}）"

    def _seedance_reference_media(self, material: Material | None) -> list[dict[str, object]]:
        if material is None:
            return []
        if material.copyright_status == CopyrightStatus.blocked:
            return []
        if material.kind not in {
            MaterialKind.video,
            MaterialKind.image,
            MaterialKind.product,
            MaterialKind.portrait,
            MaterialKind.reference,
            MaterialKind.avatar_source,
        }:
            return []
        return [
            {
                "id": material.id,
                "name": material.name,
                "kind": material.kind.value if hasattr(material.kind, "value") else str(material.kind),
                "file_path": material.file_path or "",
                "source_url": material.source_url or "",
                "copyright_status": material.copyright_status.value
                if hasattr(material.copyright_status, "value")
                else str(material.copyright_status),
            }
        ]

    def _match_tokens(self, text: str) -> set[str]:
        raw = re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]{2,}", text or "")
        tokens = {item.lower() for item in raw}
        stop = {"素材", "视频", "画面", "镜头", "生成", "场景", "展示", "一个", "这个", "hotel", "scene", "video"}
        return {token for token in tokens if token not in stop}

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

    def _configure_models_for_task(self, task: VideoTask, script: Script) -> None:
        video_scenario = "seedance_scene" if task.production_mode in {"material_mix", "seedance_scene", "digital_human"} else "preview"
        digital_scenario = task.production_mode if task.production_mode in {"talking_head_template", "digital_human"} else "preview"
        self.video_model_config = choose_model_config(self.session, "video", video_scenario)
        self.tts_model_config = choose_model_config(self.session, "tts", "voice_preview")
        self.digital_human_model_config = choose_model_config(self.session, "digital_human", digital_scenario)
        self.digital_human_platform_credential = self._active_platform_credential("volcengine", "digital_human")
        self.voice_clone_model_config = choose_model_config(self.session, "voice_clone", "digital_human")
        self.quality_model_config = choose_model_config(self.session, "video_understanding", "quality_review")
        self.media = MediaGenerationClient(
            self.video_model_config,
            self.tts_model_config,
            self.digital_human_model_config,
            self.digital_human_platform_credential,
            storage_dir=get_storage_root(self.session),
        )

    def _active_platform_credential(self, platform: str, purpose: str) -> PlatformCredential | None:
        return self.session.exec(
            select(PlatformCredential).where(
                PlatformCredential.platform == platform,
                PlatformCredential.purpose == purpose,
                PlatformCredential.is_active == True,  # noqa: E712
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
