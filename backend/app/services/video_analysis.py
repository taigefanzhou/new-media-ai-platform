from __future__ import annotations

import asyncio
import json
import math
import base64
import mimetypes
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.models.entities import Material, ReferenceVideoAnalysis
from app.services.video_skills import reference_analysis_requirements, skill_prompt_payload


@dataclass
class ReferenceAnalysisResult:
    duration_seconds: float
    width: int
    height: int
    fps: float
    has_audio: bool
    scene_count: int
    avg_shot_seconds: float
    visual_change_frequency: str
    contact_sheet_path: str
    dense_contact_sheet_path: str
    timeline_json: str
    script_analysis: str
    shooting_analysis: str
    editing_analysis: str
    reusable_template: str
    reuse_notes: str
    quality_score: float = 0
    quality_summary: str = ""
    blueprint_json: str = ""
    edit_plan_json: str = ""
    transcript: str = ""
    transcript_segments_json: str = ""
    analysis_source: str = "local"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model_enhanced: bool = False


class ReferenceVideoAnalyzer:
    def __init__(self, model_config=None) -> None:
        self.model_config = model_config

    async def analyze(
        self,
        task: ReferenceVideoAnalysis,
        material: Material,
        transcript: str = "",
    ) -> ReferenceAnalysisResult:
        if not material.file_path:
            raise RuntimeError("参考素材没有本地视频文件")
        video_path = Path(material.file_path)
        if not video_path.exists() or not video_path.is_file():
            raise RuntimeError("参考视频文件不存在")

        local_result = self._analyze_locally(video_path, transcript)
        if self._can_use_model():
            return await self._enhance_with_model(video_path, local_result, transcript)
        return local_result

    async def review_generated_output(
        self,
        video_path: str,
        requested_prompt: str,
        expected_duration_seconds: int,
    ) -> dict[str, object] | None:
        """Use the configured vision model once to review a finished generated video."""
        if not self._can_use_model():
            return None
        path = Path(video_path)
        if not path.exists() or not path.is_file():
            return None
        local_result = self._analyze_locally(path, "")
        prompt = json.dumps(
            {
                "task": "审核一条 AI 生成短视频是否可进入人工终审。",
                "expected_duration_seconds": expected_duration_seconds,
                "requested_prompt": requested_prompt[:1200],
                "contact_sheet_note": "附件为同一成片的连续抽帧，按时间从左到右、从上到下排列。",
                "requirements": [
                    "检查人脸、手部、人物轮廓是否出现明显乱码、扭曲或跨帧跳变。",
                    "检查主体、场景和动作是否明显偏离 requested_prompt。",
                    "检查画面是否清晰、无黑屏、无明显水印或大面积无关文字。",
                    "如果无法从抽帧可靠判断口型同步，必须说明，不可臆测通过。",
                    "必须返回严格 JSON，不要 Markdown。",
                ],
                "json_schema": {
                    "quality_score": "0-100 整数",
                    "decision": "passed 或 review",
                    "summary": "中文一句话结论",
                    "issues": ["中文问题描述"],
                },
            },
            ensure_ascii=False,
        )
        try:
            image_path = Path(local_result.dense_contact_sheet_path or local_result.contact_sheet_path)
            provider = (self.model_config.provider or "").lower()
            if "gemini" in provider:
                parsed, usage = await self._call_gemini_video_understanding(prompt, image_path)
            else:
                parsed, usage = await self._call_openai_compatible_vision(prompt, image_path)
        except Exception:
            return None
        score = self._safe_score(parsed.get("quality_score"), default=70)
        decision = "passed" if str(parsed.get("decision") or "").lower() == "passed" and score >= 82 else "review"
        issues = parsed.get("issues") if isinstance(parsed.get("issues"), list) else []
        summary = str(parsed.get("summary") or "视觉复核已完成。").strip()
        if issues:
            summary = f"{summary} 问题：{'；'.join(str(item) for item in issues[:3])}"
        return {
            "score": score,
            "decision": decision,
            "summary": summary,
            "usage": usage,
        }

    async def test_connection(self) -> dict[str, object]:
        if not self.model_config:
            raise RuntimeError("没有选择模型配置")
        if self.model_config.provider == "local":
            return {
                "ok": True,
                "provider": "local",
                "model_name": "local-video-analyzer",
                "quality_score": 65,
                "summary": "本地镜头/节奏分析可用；未调用外部视频理解模型。",
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }
        if not self._can_use_model():
            raise RuntimeError("请先填写接口地址、模型名和 API Key")

        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "video-understanding-test.jpg"
            self._write_test_contact_sheet(image_path)
            prompt = json.dumps(
                {
                    "task": "这是一个视频理解模型连通性测试。请判断这张抽帧测试图是否能用于参考视频拆解工作流。",
                    "requirements": [
                        "必须返回严格 JSON",
                        "ok 为 true",
                        "summary 用中文说明模型已能读取抽帧图并可用于脚本/拍摄/剪辑拆解",
                        "quality_score 给 0-100 的整数，表示模型返回内容是否符合视频拆解工作流",
                    ],
                    "json_schema": {
                        "ok": True,
                        "summary": "中文测试结论",
                        "quality_score": 90,
                    },
                },
                ensure_ascii=False,
            )
            provider = (self.model_config.provider or "").lower()
            if "gemini" in provider:
                parsed, usage = await self._call_gemini_video_understanding(prompt, image_path)
            else:
                parsed, usage = await self._call_openai_compatible_vision(prompt, image_path)
        return {
            "ok": bool(parsed.get("ok", True)),
            "provider": self.model_config.provider,
            "model_name": self.model_config.model_name,
            "quality_score": self._safe_score(parsed.get("quality_score"), default=80),
            "summary": str(parsed.get("summary") or "模型测试通过，可以用于视频理解/深度拆解。"),
            "usage": usage,
        }

    def _can_use_model(self) -> bool:
        if not self.model_config:
            return False
        if not self.model_config.api_base or not self.model_config.api_key:
            return False
        return self.model_config.provider != "local"

    def _analyze_locally(self, video_path: Path, transcript: str) -> ReferenceAnalysisResult:
        from moviepy.editor import VideoFileClip

        clip = VideoFileClip(str(video_path))
        try:
            duration = float(clip.duration or 0)
            width = int(clip.w or 0)
            height = int(clip.h or 0)
            fps = float(clip.fps or 0)
            has_audio = clip.audio is not None
            analysis_dir = video_path.parent / "deep-analysis"
            analysis_dir.mkdir(parents=True, exist_ok=True)

            sample_times = self._sample_times(duration, interval=1.5, max_samples=90)
            sampled = [(time, self._frame_image(clip, time)) for time in sample_times]
            cuts = self._detect_visual_cuts(sampled)
            timeline = self._build_timeline(duration, cuts, sampled, transcript)

            contact_sheet_path = analysis_dir / "analysis_contact_sheet.jpg"
            dense_contact_sheet_path = analysis_dir / "analysis_dense_contact_sheet.jpg"
            self._write_contact_sheet(clip, duration, contact_sheet_path, max_frames=24, cols=6)
            self._write_contact_sheet(clip, duration, dense_contact_sheet_path, max_frames=36, cols=4)

            scene_count = max(1, len(timeline))
            avg_shot = round(duration / scene_count, 2) if scene_count else 0
            visual_frequency = self._visual_frequency_label(avg_shot)
            script_analysis = self._script_analysis(transcript, duration, timeline)
            shooting_analysis = self._shooting_analysis(width, height, fps, timeline)
            editing_analysis = self._editing_analysis(duration, scene_count, avg_shot, visual_frequency, timeline)
            reusable_template = self._reusable_template(duration, timeline, transcript)
            reuse_notes = self._reuse_notes(timeline)
            blueprint = self._default_blueprint(
                script_analysis,
                shooting_analysis,
                reusable_template,
                reuse_notes,
                timeline,
            )
            edit_plan = self._default_edit_plan(timeline)
            transcript_segments = self._default_transcript_segments(transcript, duration)
            quality_score, quality_summary = self._local_quality_score(
                duration=duration,
                width=width,
                height=height,
                has_audio=has_audio,
                scene_count=scene_count,
                transcript=transcript,
            )

            return ReferenceAnalysisResult(
                duration_seconds=round(duration, 2),
                width=width,
                height=height,
                fps=round(fps, 2),
                has_audio=has_audio,
                scene_count=scene_count,
                avg_shot_seconds=avg_shot,
                visual_change_frequency=visual_frequency,
                contact_sheet_path=str(contact_sheet_path),
                dense_contact_sheet_path=str(dense_contact_sheet_path),
                timeline_json=json.dumps(timeline, ensure_ascii=False),
                script_analysis=script_analysis,
                shooting_analysis=shooting_analysis,
                editing_analysis=editing_analysis,
                reusable_template=reusable_template,
                reuse_notes=reuse_notes,
                quality_score=quality_score,
                quality_summary=quality_summary,
                blueprint_json=json.dumps(blueprint, ensure_ascii=False),
                edit_plan_json=json.dumps(edit_plan, ensure_ascii=False),
                transcript=transcript,
                transcript_segments_json=json.dumps(transcript_segments, ensure_ascii=False),
                analysis_source="local",
            )
        finally:
            clip.close()

    async def _enhance_with_model(
        self,
        video_path: Path,
        local_result: ReferenceAnalysisResult,
        transcript: str,
    ) -> ReferenceAnalysisResult:
        provider = (self.model_config.provider or "").lower()
        prompt = self._model_analysis_prompt(video_path, local_result, transcript)
        image_path = Path(local_result.dense_contact_sheet_path or local_result.contact_sheet_path)
        try:
            if self._is_volcengine_ark(provider):
                try:
                    parsed, usage = await self._call_volcengine_video_understanding(
                        prompt,
                        video_path,
                        local_result.duration_seconds,
                    )
                    source = "full_video"
                except Exception:
                    parsed, usage = await self._call_openai_compatible_vision(prompt, image_path)
                    source = "contact_sheet"
            elif "gemini" in provider:
                parsed, usage = await self._call_gemini_video_understanding(prompt, image_path)
                source = "contact_sheet"
            else:
                parsed, usage = await self._call_openai_compatible_vision(prompt, image_path)
                source = "contact_sheet"

            should_review = local_result.duration_seconds <= 180 or self._safe_score(
                parsed.get("quality_score"), default=0
            ) < 82
            if should_review:
                try:
                    review_prompt = self._deep_review_prompt(parsed, local_result.duration_seconds)
                    if "gemini" in provider:
                        review, review_usage = await self._call_gemini_video_understanding(review_prompt, image_path)
                    else:
                        review, review_usage = await self._call_openai_compatible_vision(review_prompt, image_path)
                    parsed = self._merge_deep_review_payload(parsed, review)
                    usage = self._sum_usage(usage, review_usage)
                    source += "_deep"
                except Exception:
                    pass
            local_result.analysis_source = source
        except Exception as exc:
            detail = str(exc).strip() or exc.__class__.__name__
            raise RuntimeError(f"视频理解模型增强失败，未使用本地结果代替真实模型：{detail}") from exc

        return self._merge_model_analysis(local_result, parsed, usage)

    def _model_analysis_prompt(
        self,
        video_path: Path,
        local_result: ReferenceAnalysisResult,
        transcript: str,
    ) -> str:
        return json.dumps(
            {
                "task": "分析参考短视频的脚本方案、拍摄方式、剪辑方式，并输出可复用但不搬运的原创模板。",
                "source_file": video_path.name,
                "metadata": {
                    "duration_seconds": local_result.duration_seconds,
                    "width": local_result.width,
                    "height": local_result.height,
                    "fps": local_result.fps,
                    "has_audio": local_result.has_audio,
                    "scene_count": local_result.scene_count,
                    "avg_shot_seconds": local_result.avg_shot_seconds,
                    "visual_change_frequency": local_result.visual_change_frequency,
                },
                "built_in_video_production_skills": skill_prompt_payload(),
                "local_timeline": json.loads(local_result.timeline_json or "[]"),
                "transcript": transcript,
                "requirements": [
                    *reference_analysis_requirements(),
                    "只学习结构、节奏、拍摄和剪辑方法，不复刻原视频原文、人物、画面或商家信息。",
                    "重点拆解：开头如何抓人、论点如何推进、证据画面如何穿插、字幕/关键词如何设计。",
                    "拍摄方式要说清楚人物景别、机位、背景、表情、手势、屏幕录制或B-roll的使用。",
                    "剪辑方式要说清楚每几秒发生视觉变化、如何切截图/卡片/人物、如何保持口播不断线。",
                    "生成的 reusable_template 要能直接给脚本生成模块使用。",
                    "reference_blueprint 必须是结构化对象，完整记录内容策略、视觉、字幕、音频和合规边界。",
                    "edit_plan 必须按时间顺序给出可执行剪辑动作，可直接交给系统内 Remotion/FFmpeg 渲染。",
                    "如果能听清视频音频，transcript 必须给出完整口播，transcript_segments 必须给出对应时间段；已有 transcript 只能作为校对参考。",
                    "每个镜头结论必须尽量绑定口播、画面文字、人物动作或声音证据，并给出 0-100 置信度；看不清或听不清时明确标记。",
                    "区分内容吸引力和客观播放数据：只能分析留存作用与风险，不得伪造真实完播率或用户数据。",
                    "必须输出严格 JSON，不要使用 Markdown。",
                ],
                "json_schema": {
                    "script_analysis": "脚本结构和叙事方法分析，中文，多行文本",
                    "shooting_analysis": "拍摄方式分析，中文，多行文本",
                    "editing_analysis": "剪辑方式分析，中文，多行文本",
                    "reusable_template": "可复用原创模板，中文，多行文本",
                    "reuse_notes": "可学习/不可搬运/合规注意，中文，多行文本",
                    "quality_score": "0-100 的数字，评价这次拆解是否足够指导原创视频生产",
                    "quality_summary": "中文，一句话说明评分原因和下一步优化建议",
                    "transcript": "完整口播文本；没有语音则为空字符串",
                    "transcript_segments": [
                        {"start_second": 0, "end_second": 3.2, "text": "口播内容", "speaker": "speaker_1", "estimated": False}
                    ],
                    "reference_blueprint": {
                        "hook": "开场钩子及其有效原因",
                        "audience": "目标观众",
                        "narrative_structure": ["叙事阶段及作用"],
                        "visual_style": "人物、场景、构图、运镜和色彩规律",
                        "caption_style": "字幕位置、断句、字号层级、强调方式",
                        "audio_style": "口播、音乐、环境声、音效和节奏规律",
                        "reusable_rules": ["可复用的结构和方法"],
                        "compliance_limits": ["不可复制的人物、台词、音乐、标识和画面"],
                    },
                    "edit_plan": [
                        {
                            "start_second": 0,
                            "end_second": 5,
                            "action": "keep / trim / replace / overlay",
                            "visual": "主画面或B-roll要求",
                            "caption": "字幕与关键词强调",
                            "transition": "hard_cut / J_cut / L_cut / dissolve",
                            "audio": "口播、BGM、环境声或音效操作",
                        }
                    ],
                    "timeline": [
                        {
                            "index": 1,
                            "start_second": 0,
                            "end_second": 5,
                            "visual_role": "画面角色",
                            "script_function": "脚本作用",
                            "shot_type": "景别和机位",
                            "camera_movement": "运镜方式",
                            "person_action": "人物动作、表情和视线",
                            "transcript_excerpt": "这一时段对应的口播原文或语义摘要",
                            "caption": "字幕内容、位置和强调词",
                            "audio": "口播、音乐、环境声和音效",
                            "material_role": "数字人、产品、场景、证据或过渡素材",
                            "engagement_reason": "这一段为什么能留住观众",
                            "evidence": "支撑判断的口播、画面文字、人物动作或声音证据",
                            "retention_score": "0-100 留存作用强度，不代表真实平台数据",
                            "confidence": "0-100 判断置信度",
                            "weakness": "这一段可能流失观众的原因",
                            "optimization": "保持原意时可执行的优化动作",
                            "editing_note": "剪辑手法",
                            "reuse_instruction": "原创复用方式",
                        }
                    ],
                },
            },
            ensure_ascii=False,
        )

    def _deep_review_prompt(self, primary: dict[str, object], duration_seconds: float) -> str:
        timeline = primary.get("timeline") if isinstance(primary.get("timeline"), list) else []
        transcript_segments = (
            primary.get("transcript_segments") if isinstance(primary.get("transcript_segments"), list) else []
        )
        snapshot = {
            "script_analysis": str(primary.get("script_analysis") or "")[:3000],
            "shooting_analysis": str(primary.get("shooting_analysis") or "")[:2000],
            "editing_analysis": str(primary.get("editing_analysis") or "")[:2000],
            "reference_blueprint": primary.get("reference_blueprint") or {},
            "timeline": timeline[:60],
            "transcript_segments": transcript_segments[:80],
        }
        return json.dumps(
            {
                "task": "对第一轮参考视频拆解做证据复核。重新查看按时间排列的密集抽帧，只保留能由具体时间段、画面或已有转写支持的结论。",
                "video_type": "短视频" if duration_seconds <= 180 else "长视频",
                "duration_seconds": duration_seconds,
                "first_pass": snapshot,
                "requirements": [
                    "重点复查开场钩子、关键转折、证据展示、高潮和行动引导，最多返回 8 个关键时刻。",
                    "每个关键时刻必须给出明确时间范围，以及口播、视觉、画面文字、声音四类证据；没有证据的字段留空。",
                    "抽帧不能独立证明声音变化；声音证据只能引用第一轮转写或分析，否则写入 missing_evidence。",
                    "retention_score 只是基于内容结构的留存作用强度，不得声称是真实播放数据。",
                    "发现第一轮结论与视频不一致时写入 contradictions，并给出修正结论。",
                    "replication_plan 只复用结构、节奏和镜头方法，必须替换原文、人物、商家、音乐、标识和原画面。",
                    "看不清、听不清或无法确认时写入 missing_evidence，不得臆测。",
                    "必须输出严格 JSON，不要 Markdown。",
                ],
                "json_schema": {
                    "review_summary": "中文总结这条视频为什么有效、哪里薄弱以及最值得复用的方法",
                    "evidence_coverage_score": "0-100，结论被音视频证据覆盖的程度",
                    "confidence_score": "0-100，本次复核整体置信度",
                    "critical_moments": [
                        {
                            "start_second": 0,
                            "end_second": 3,
                            "role": "hook / turn / proof / climax / cta",
                            "evidence": {
                                "transcript": "对应口播",
                                "visual": "对应画面和人物动作",
                                "on_screen_text": "画面文字",
                                "audio": "音乐、音效或声音变化",
                            },
                            "retention_score": "0-100 留存作用强度",
                            "retention_reason": "为何可能让观众继续观看",
                            "weakness": "可能造成流失的因素",
                            "recommendation": "可执行优化建议",
                            "confidence": "0-100",
                        }
                    ],
                    "retention_curve": [
                        {
                            "start_second": 0,
                            "end_second": 3,
                            "stage": "钩子",
                            "strength": "strong / medium / weak",
                            "reason": "判断依据",
                        }
                    ],
                    "contradictions": [
                        {"first_pass_claim": "第一轮结论", "evidence": "反证", "correction": "修正结论"}
                    ],
                    "missing_evidence": ["无法确认的内容"],
                    "replication_plan": {
                        "opening_template": "原创开场结构",
                        "narrative_steps": ["原创叙事步骤"],
                        "shot_rhythm": "镜头节奏规则",
                        "caption_rules": ["字幕规则"],
                        "audio_rules": ["声音规则"],
                        "must_replace": ["必须替换的参考视频元素"],
                    },
                },
            },
            ensure_ascii=False,
        )

    def _merge_deep_review_payload(
        self,
        primary: dict[str, object],
        review: dict[str, object],
    ) -> dict[str, object]:
        if not review:
            return primary
        blueprint = primary.get("reference_blueprint")
        if not isinstance(blueprint, dict):
            blueprint = {}
        blueprint["deep_review"] = review
        primary["reference_blueprint"] = blueprint

        moments = review.get("critical_moments")
        timeline = primary.get("timeline")
        if not isinstance(moments, list) or not isinstance(timeline, list):
            return primary
        valid_moments = [item for item in moments if isinstance(item, dict)]
        for segment in timeline:
            if not isinstance(segment, dict):
                continue
            start = float(segment.get("start_second") or 0)
            end = float(segment.get("end_second") or start)
            overlaps = [
                item
                for item in valid_moments
                if float(item.get("end_second") or 0) > start
                and float(item.get("start_second") or 0) < end
            ]
            if not overlaps:
                continue
            moment = max(
                overlaps,
                key=lambda item: min(end, float(item.get("end_second") or end))
                - max(start, float(item.get("start_second") or start)),
            )
            segment["evidence"] = moment.get("evidence") or segment.get("evidence") or ""
            for key in ("retention_score", "confidence", "weakness"):
                if moment.get(key) not in (None, ""):
                    segment[key] = moment[key]
            if moment.get("recommendation"):
                segment["optimization"] = moment["recommendation"]
        return primary

    @staticmethod
    def _sum_usage(*usage_items: dict[str, object]) -> dict[str, int]:
        return {
            key: sum(int(item.get(key) or 0) for item in usage_items)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        }

    def _is_volcengine_ark(self, provider: str) -> bool:
        api_base = (self.model_config.api_base or "").lower() if self.model_config else ""
        return "volcengine" in provider or provider in {"ark", "doubao"} or "volces.com/api/v3" in api_base

    async def _call_volcengine_video_understanding(
        self,
        prompt: str,
        video_path: Path,
        duration_seconds: float,
    ) -> tuple[dict, dict]:
        if video_path.stat().st_size > 512 * 1024 * 1024:
            raise RuntimeError("参考视频超过方舟 Files API 的 512MB 上限，请先压缩或配置 TOS 大文件存储。")
        api_base = self._ark_api_base(self.model_config.api_base)
        headers = {"Authorization": f"Bearer {self.model_config.api_key}"}
        mime_type = mimetypes.guess_type(video_path.name)[0] or "video/mp4"
        fps = 1.0 if duration_seconds <= 120 else 0.5 if duration_seconds <= 600 else 0.3
        file_id = ""
        async with httpx.AsyncClient(timeout=httpx.Timeout(150, connect=30), trust_env=False) as client:
            try:
                with video_path.open("rb") as source:
                    upload = await client.post(
                        api_base + "/files",
                        headers=headers,
                        data={"purpose": "user_data", "preprocess_configs[video][fps]": str(fps)},
                        files={"file": (video_path.name, source, mime_type)},
                    )
                upload.raise_for_status()
                file_data = upload.json()
                file_id = str(file_data.get("id") or "")
                if not file_id:
                    raise RuntimeError("方舟 Files API 未返回 file id")

                status = str(file_data.get("status") or "processing")
                for _ in range(150):
                    if status not in {"processing", "queued", "pending"}:
                        break
                    await asyncio.sleep(2)
                    file_response = await client.get(api_base + f"/files/{file_id}", headers=headers)
                    file_response.raise_for_status()
                    file_data = file_response.json()
                    status = str(file_data.get("status") or "")
                if status not in {"active", "processed", "completed", "succeeded", "success"}:
                    raise RuntimeError(f"方舟视频文件处理失败：{status or 'timeout'}")

                response = await client.post(
                    api_base + "/responses",
                    headers={**headers, "Content-Type": "application/json"},
                    json={
                        "model": self.model_config.model_name,
                        "thinking": {"type": "disabled"},
                        "max_output_tokens": 6000,
                        "input": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "input_video", "file_id": file_id},
                                    {"type": "input_text", "text": prompt},
                                ],
                            }
                        ],
                    },
                )
                response.raise_for_status()
                data = response.json()
                parsed = self._loads_json_loose(self._responses_output_text(data))
                usage_data = data.get("usage") or {}
                usage = {
                    "prompt_tokens": usage_data.get("input_tokens") or 0,
                    "completion_tokens": usage_data.get("output_tokens") or 0,
                    "total_tokens": usage_data.get("total_tokens") or 0,
                }
            finally:
                if file_id:
                    try:
                        await client.delete(api_base + f"/files/{file_id}", headers=headers)
                    except httpx.HTTPError:
                        pass
        return parsed, usage

    def _ark_api_base(self, api_base: str) -> str:
        normalized = api_base.rstrip("/")
        for suffix in ("/chat/completions", "/responses", "/files"):
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)]
        return normalized

    def _responses_output_text(self, data: dict) -> str:
        direct = data.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct
        parts: list[str] = []
        for item in data.get("output") or []:
            if not isinstance(item, dict):
                continue
            for content in item.get("content") or []:
                if not isinstance(content, dict):
                    continue
                text = content.get("text")
                if content.get("type") in {"output_text", "text"} and isinstance(text, str):
                    parts.append(text)
        if not parts:
            raise RuntimeError("方舟 Responses API 未返回视频分析文本")
        return "\n".join(parts)

    async def _call_openai_compatible_vision(self, prompt: str, image_path: Path) -> tuple[dict, dict]:
        api_base = self.model_config.api_base.rstrip("/")
        api_key = self.model_config.api_key
        model_name = self.model_config.model_name
        image_data = self._image_data_uri(image_path)
        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "你是短视频导演和剪辑分析师，擅长把参考视频拆解成可执行的原创拍摄模板。",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_data}},
                    ],
                },
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=180) as client:
            endpoint = api_base if api_base.endswith("/chat/completions") else api_base + "/chat/completions"
            response = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        content = data["choices"][0]["message"]["content"]
        return self._loads_json_loose(content), data.get("usage") or {}

    async def _call_gemini_video_understanding(self, prompt: str, image_path: Path) -> tuple[dict, dict]:
        api_base = self.model_config.api_base.rstrip("/")
        api_key = self.model_config.api_key
        model_name = self.model_config.model_name
        image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        url = f"{api_base}/models/{model_name}:generateContent?key={api_key}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}},
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
        content = data["candidates"][0]["content"]["parts"][0]["text"]
        usage_metadata = data.get("usageMetadata") or {}
        usage = {
            "prompt_tokens": usage_metadata.get("promptTokenCount") or 0,
            "completion_tokens": usage_metadata.get("candidatesTokenCount") or 0,
            "total_tokens": usage_metadata.get("totalTokenCount") or 0,
        }
        return self._loads_json_loose(content), usage

    def _merge_model_analysis(
        self,
        local_result: ReferenceAnalysisResult,
        parsed: dict,
        usage: dict,
    ) -> ReferenceAnalysisResult:
        timeline = parsed.get("timeline")
        if isinstance(timeline, list):
            timeline = [item for item in timeline if isinstance(item, dict)]
        if timeline:
            local_result.timeline_json = json.dumps(timeline, ensure_ascii=False)
            local_result.scene_count = len(timeline)
            local_result.avg_shot_seconds = round(local_result.duration_seconds / len(timeline), 2)
            local_result.visual_change_frequency = self._visual_frequency_label(local_result.avg_shot_seconds)
        else:
            timeline = json.loads(local_result.timeline_json or "[]")
        for field_name in ("script_analysis", "shooting_analysis", "editing_analysis", "reusable_template", "reuse_notes"):
            value = parsed.get(field_name)
            if isinstance(value, str) and value.strip():
                setattr(local_result, field_name, value.strip())
        blueprint = parsed.get("reference_blueprint")
        if not isinstance(blueprint, dict):
            blueprint = self._default_blueprint(
                local_result.script_analysis,
                local_result.shooting_analysis,
                local_result.reusable_template,
                local_result.reuse_notes,
                timeline,
            )
        edit_plan = parsed.get("edit_plan")
        if isinstance(edit_plan, list):
            edit_plan = [item for item in edit_plan if isinstance(item, dict)]
        if not edit_plan:
            edit_plan = self._default_edit_plan(timeline)
        local_result.blueprint_json = json.dumps(blueprint, ensure_ascii=False)
        local_result.edit_plan_json = json.dumps(edit_plan, ensure_ascii=False)
        model_transcript = parsed.get("transcript")
        if isinstance(model_transcript, str) and model_transcript.strip():
            local_result.transcript = model_transcript.strip()
        transcript_segments = parsed.get("transcript_segments")
        if isinstance(transcript_segments, list):
            transcript_segments = [item for item in transcript_segments if isinstance(item, dict)]
        if not transcript_segments:
            transcript_segments = self._default_transcript_segments(local_result.transcript, local_result.duration_seconds)
        local_result.transcript_segments_json = json.dumps(transcript_segments, ensure_ascii=False)
        local_result.quality_score = self._safe_score(parsed.get("quality_score"), default=local_result.quality_score)
        quality_summary = parsed.get("quality_summary")
        if isinstance(quality_summary, str) and quality_summary.strip():
            local_result.quality_summary = quality_summary.strip()
        local_result.prompt_tokens = int(usage.get("prompt_tokens") or usage.get("promptTokenCount") or 0)
        local_result.completion_tokens = int(usage.get("completion_tokens") or usage.get("completionTokenCount") or 0)
        local_result.total_tokens = int(usage.get("total_tokens") or usage.get("totalTokenCount") or 0)
        local_result.model_enhanced = True
        return local_result

    def _default_blueprint(
        self,
        script_analysis: str,
        shooting_analysis: str,
        reusable_template: str,
        reuse_notes: str,
        timeline: list[dict[str, object]],
    ) -> dict[str, object]:
        return {
            "hook": script_analysis,
            "narrative_structure": [item.get("script_function", "") for item in timeline],
            "visual_style": shooting_analysis,
            "caption_style": "按语义短句断行，关键词强调，避开人物面部和产品主体。",
            "audio_style": "口播优先，BGM自动压低，转场只在叙事节点使用。",
            "reusable_rules": [reusable_template],
            "compliance_limits": [reuse_notes],
        }

    def _default_edit_plan(self, timeline: list[dict[str, object]]) -> list[dict[str, object]]:
        return [
            {
                "start_second": item.get("start_second", 0),
                "end_second": item.get("end_second", 0),
                "action": "keep",
                "visual": item.get("reuse_instruction") or item.get("visual_role") or "",
                "caption": item.get("script_function") or "",
                "transition": "hard_cut",
                "audio": "narration_priority",
            }
            for item in timeline
        ]

    def _default_transcript_segments(self, transcript: str, duration_seconds: float) -> list[dict[str, object]]:
        sentences = [item.strip() for item in re.split(r"(?<=[。！？!?])", transcript) if item.strip()]
        total_chars = sum(len(item) for item in sentences)
        if not sentences or total_chars <= 0 or duration_seconds <= 0:
            return []
        cursor = 0.0
        segments: list[dict[str, object]] = []
        for sentence in sentences:
            span = duration_seconds * len(sentence) / total_chars
            end = min(duration_seconds, cursor + span)
            segments.append(
                {
                    "start_second": round(cursor, 2),
                    "end_second": round(end, 2),
                    "text": sentence,
                    "speaker": "speaker_1",
                    "estimated": True,
                }
            )
            cursor = end
        return segments

    def _image_data_uri(self, image_path: Path) -> str:
        image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return f"data:image/jpeg;base64,{image_b64}"

    def _loads_json_loose(self, content: str) -> dict:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}")
            if start >= 0 and end > start:
                return json.loads(content[start : end + 1])
            raise

    def _safe_score(self, value: object, default: float = 0) -> float:
        try:
            return max(0.0, min(100.0, float(value)))
        except (TypeError, ValueError):
            return default

    def _local_quality_score(
        self,
        duration: float,
        width: int,
        height: int,
        has_audio: bool,
        scene_count: int,
        transcript: str,
    ) -> tuple[float, str]:
        score = 45.0
        reasons: list[str] = []
        if duration >= 20:
            score += 12
            reasons.append("视频时长足够拆解结构")
        if height >= width:
            score += 10
            reasons.append("竖版画幅适合抖音/视频号参考")
        if has_audio:
            score += 10
            reasons.append("包含音频，可继续结合转写分析口播")
        if scene_count >= 5:
            score += 12
            reasons.append("检测到多个视觉段落")
        if transcript.strip():
            score += 8
            reasons.append("已有转写稿，脚本结构判断更完整")
        score = min(100.0, round(score, 1))
        if not reasons:
            reasons.append("已完成基础抽帧和节奏拆解")
        return score, "本地基础评分：" + "、".join(reasons) + "。"

    def _write_test_contact_sheet(self, output_path: Path) -> None:
        width, height = 720, 1280
        thumb_w, thumb_h = 180, 320
        sheet = Image.new("RGB", (thumb_w * 4, thumb_h + 42), "white")
        draw = ImageDraw.Draw(sheet)
        font = self._font(16)
        frames = [
            ("0s 开场口播", (31, 92, 150)),
            ("5s 数据截图", (24, 132, 117)),
            ("10s 客房场景", (230, 160, 64)),
            ("15s 总结引导", (120, 76, 160)),
        ]
        for index, (label, color) in enumerate(frames):
            x = index * thumb_w
            frame = Image.new("RGB", (width, height), color)
            frame_draw = ImageDraw.Draw(frame)
            frame_draw.rectangle((60, 120, width - 60, 280), fill=(255, 255, 255))
            frame_draw.text((90, 170), label, fill=(20, 30, 40), font=self._font(42))
            frame_draw.rectangle((80, height - 260, width - 80, height - 170), fill=(20, 30, 40))
            frame_draw.text((110, height - 235), "reference video analysis", fill=(255, 255, 255), font=self._font(36))
            thumb = self._cover(frame, thumb_w, thumb_h)
            sheet.paste(thumb, (x, 0))
            draw.text((x + 8, thumb_h + 10), label, fill=(20, 20, 20), font=font)
        sheet.save(output_path, quality=90)

    def _sample_times(self, duration: float, interval: float = 1.5, max_samples: int = 90) -> list[float]:
        if duration <= 0:
            return [0]
        count = min(max_samples, max(4, math.ceil(duration / interval)))
        return [min(duration - 0.05, index * duration / count) for index in range(count)]

    def _frame_image(self, clip, time: float) -> Image.Image:
        frame = clip.get_frame(max(0, min(time, clip.duration - 0.05)))
        return Image.fromarray(frame).convert("RGB")

    def _detect_visual_cuts(self, sampled: list[tuple[float, Image.Image]]) -> list[float]:
        if len(sampled) < 3:
            return []
        scores: list[tuple[float, float]] = []
        previous = self._frame_vector(sampled[0][1])
        for time, image in sampled[1:]:
            current = self._frame_vector(image)
            score = float(np.mean(np.abs(current - previous)))
            scores.append((time, score))
            previous = current
        raw_scores = np.array([score for _, score in scores])
        threshold = max(0.085, float(raw_scores.mean() + raw_scores.std() * 1.1))
        cuts: list[float] = []
        last_cut = -999.0
        for time, score in scores:
            if score >= threshold and time - last_cut >= 2.0:
                cuts.append(round(time, 2))
                last_cut = time
        return cuts

    def _frame_vector(self, image: Image.Image) -> np.ndarray:
        resized = image.resize((96, 170), Image.Resampling.LANCZOS).convert("RGB")
        arr = np.asarray(resized, dtype=np.float32) / 255.0
        hist_parts = []
        for channel in range(3):
            hist, _ = np.histogram(arr[:, :, channel], bins=16, range=(0.0, 1.0), density=True)
            hist_parts.append(hist)
        # Include a coarse center patch to capture overlays/screenshot changes.
        center = arr[arr.shape[0] // 4 : arr.shape[0] * 3 // 4, arr.shape[1] // 4 : arr.shape[1] * 3 // 4]
        return np.concatenate([*hist_parts, center.mean(axis=(0, 1)), center.std(axis=(0, 1))])

    def _build_timeline(
        self,
        duration: float,
        cuts: list[float],
        sampled: list[tuple[float, Image.Image]],
        transcript: str,
    ) -> list[dict[str, object]]:
        boundaries = [0.0, *[time for time in cuts if 0 < time < duration - 1], round(duration, 2)]
        if len(boundaries) <= 2:
            boundaries = self._even_boundaries(duration)
        timeline: list[dict[str, object]] = []
        for index, start in enumerate(boundaries[:-1]):
            end = boundaries[index + 1]
            if end - start < 1:
                continue
            mid = (start + end) / 2
            nearest = min(sampled, key=lambda item: abs(item[0] - mid))[1] if sampled else None
            role = self._segment_role(index, len(boundaries) - 1, nearest, end - start)
            timeline.append(
                {
                    "index": index + 1,
                    "start_second": round(start, 2),
                    "end_second": round(end, 2),
                    "duration_seconds": round(end - start, 2),
                    "visual_role": role,
                    "script_function": self._script_function(index, len(boundaries) - 1),
                    "editing_note": self._editing_note_for_role(role, end - start),
                    "reuse_instruction": self._reuse_instruction_for_role(role),
                }
            )
        return timeline

    def _even_boundaries(self, duration: float) -> list[float]:
        segment = 6 if duration <= 90 else 10
        count = max(4, min(18, math.ceil(duration / segment)))
        return [round(index * duration / count, 2) for index in range(count)] + [round(duration, 2)]

    def _segment_role(
        self,
        index: int,
        total: int,
        image: Optional[Image.Image],
        segment_duration: float,
    ) -> str:
        if index == 0:
            return "开场口播/主题标题"
        if index >= total - 1:
            return "回到人物总结/关注引导"
        if segment_duration <= 3.2:
            return "快切证据画面/B-roll"
        if index % 4 == 0:
            return "平台截图/数据证据"
        if index % 3 == 0:
            return "关键词卡片/编号方法"
        return "主体口播/解释承接"

    def _script_function(self, index: int, total: int) -> str:
        if index == 0:
            return "钩子：先抛结论或痛点，让观众知道为什么要继续看"
        if index >= total - 1:
            return "收束：总结方法，给出行动建议或关注理由"
        if index <= max(1, total * 0.25):
            return "铺垫：解释背景、场景或问题"
        if index <= max(2, total * 0.65):
            return "展开：给出证据、案例、截图或方法"
        return "强化：用清单、数据或场景把观点讲实"

    def _editing_note_for_role(self, role: str, duration: float) -> str:
        if "快切" in role:
            return "短时插入，保持口播不断线，用画面证明刚才说的话"
        if "截图" in role:
            return "截图应局部放大、滚动或加高亮，避免静态贴图"
        if "卡片" in role:
            return "用编号、勾选或关键词卡片降低理解成本"
        if "总结" in role:
            return "回到人物正面，手势和字幕一起强化结论"
        return "人物稳定出镜，字幕同步，必要时叠加小图或侧边证据"

    def _reuse_instruction_for_role(self, role: str) -> str:
        if "截图" in role:
            return "替换为本行业的订单页、后台页、地图页、价格页或能耗看板"
        if "B-roll" in role:
            return "替换为酒店大堂、客房、前台、入住、智能设备联动画面"
        if "卡片" in role:
            return "提炼为 2-3 个关键词，例如节能、体验、管理、复购"
        if "开场" in role:
            return "用一句行业痛点开场，不复刻原视频原话"
        return "保留口播承接关系，换成自己的观点和业务素材"

    def _visual_frequency_label(self, avg_shot: float) -> str:
        if avg_shot <= 3.5:
            return "快节奏：约 3 秒左右一次视觉变化"
        if avg_shot <= 6:
            return "短视频常规节奏：约 3-6 秒一次视觉变化"
        if avg_shot <= 10:
            return "稳态讲解节奏：约 6-10 秒一次视觉变化"
        return "慢节奏：主要依赖口播和字幕承接"

    def _script_analysis(self, transcript: str, duration: float, timeline: list[dict[str, object]]) -> str:
        if transcript.strip():
            first_line = transcript.strip().replace("\n", " ")[:80]
            hook = f"口播开头可围绕“{first_line}”提炼钩子。"
        else:
            hook = "当前未取得逐字稿，建议接入 ASR 后按逐字时间轴拆开头钩子、论点和转化句。"
        return "\n".join(
            [
                hook,
                f"结构判断：约 {round(duration, 1)} 秒，适合拆成“钩子-背景-证据-方法-总结”五段。",
                "脚本精髓：不是平铺直叙，而是每讲一个观点就配一个证据画面或关键词卡片。",
                "复用方式：我们生成酒店视频时，应让 AI 先写口播主线，再给每 3-6 秒安排证据画面。",
                "内置 Skill：只学习参考视频的结构、节奏、镜头角色和字幕策略，不搬运原文、人物或商家画面。",
            ]
        )

    def _shooting_analysis(self, width: int, height: int, fps: float, timeline: list[dict[str, object]]) -> str:
        ratio = "竖版" if height >= width else "横版"
        return "\n".join(
            [
                f"画幅：{width}x{height}，{ratio}，适合手机信息流观看。",
                "人物拍摄：建议中景或半身，眼神看镜头，背景选择酒店大堂、办公室、客房或洽谈区。",
                "动作设计：手势只在强调数字、步骤和关键词时出现，避免全程僵硬坐姿。",
                f"帧率：约 {round(fps, 1)}fps，常规短视频帧率即可，重点是稳定光线和清晰收音。",
            ]
        )

    def _editing_analysis(
        self,
        duration: float,
        scene_count: int,
        avg_shot: float,
        visual_frequency: str,
        timeline: list[dict[str, object]],
    ) -> str:
        return "\n".join(
            [
                f"剪辑节奏：检测到约 {scene_count} 个视觉段落，平均 {avg_shot} 秒一段，{visual_frequency}。",
                "剪辑手法：人物口播作为主线，穿插截图、B-roll、关键词卡片，视觉变化服务于观点，不抢口播。",
                "字幕方式：底部字幕全程跟随，关键字可用高亮色；标题区保持统一，形成系列记忆点。",
                "转场方式：不需要复杂特效，建议用截图滑入、局部放大、勾选卡片和轻微推拉镜头。",
            ]
        )

    def _reusable_template(self, duration: float, timeline: list[dict[str, object]], transcript: str) -> str:
        return "\n".join(
            [
                "模板名称：竖版口播增强模板",
                "1. 开场 0-3 秒：人物出镜 + 大标题 + 一句结论或痛点。",
                "2. 中段：每个观点后插入截图、场景或关键词卡片，保持 3-6 秒一次视觉变化。",
                "3. 证据：用平台页、订单页、后台看板、客房/前台/B-roll 证明观点。",
                "4. 总结：回到人物正面，给出行动建议，最后做关注或咨询引导。",
                "5. 生成规则：AI 生成脚本时必须同步输出“口播稿 + 分镜时间轴 + 证据素材清单 + 字幕重点词”。",
                "6. 质检规则：底片无内嵌文字和水印；字幕后期统一添加；成片检查脸部、嘴形、背景和脚本一致性。",
            ]
        )

    def _reuse_notes(self, timeline: list[dict[str, object]]) -> str:
        roles = [str(item.get("visual_role", "")) for item in timeline]
        return "\n".join(
            [
                "可学习：节奏、结构、字幕位置、证据插入方式、关键词卡片方式。",
                "不可直接搬运：原视频画面、人物形象、原文字幕、平台截图里的具体商家信息。",
                "生成脚本时：必须换成自己的业务观点、数字人身份、素材库画面和后期字幕。",
                f"本条视频的可复用视觉角色：{'、'.join(dict.fromkeys(roles))}",
            ]
        )

    def _write_contact_sheet(self, clip, duration: float, output_path: Path, max_frames: int, cols: int) -> None:
        count = min(max_frames, max(8, math.ceil(duration / 3)))
        times = [min(duration - 0.05, index * duration / count) for index in range(count)]
        if clip.h >= clip.w:
            thumb_w, thumb_h = 180, 320
        else:
            thumb_w = 220
            thumb_h = round(thumb_w * clip.h / max(1, clip.w))
        rows = math.ceil(count / cols)
        footer_h = 26
        sheet = Image.new("RGB", (cols * thumb_w, rows * (thumb_h + footer_h)), "white")
        draw = ImageDraw.Draw(sheet)
        font = self._font(14)
        for index, time in enumerate(times):
            frame = self._frame_image(clip, time)
            thumb = self._cover(frame, thumb_w, thumb_h)
            x = (index % cols) * thumb_w
            y = (index // cols) * (thumb_h + footer_h)
            sheet.paste(thumb, (x, y))
            draw.text((x + 6, y + thumb_h + 4), f"{time:05.1f}s", fill=(20, 20, 20), font=font)
        sheet.save(output_path, quality=92)

    def _cover(self, image: Image.Image, width: int, height: int) -> Image.Image:
        scale = max(width / image.width, height / image.height)
        resized = image.resize((int(image.width * scale), int(image.height * scale)), Image.Resampling.LANCZOS)
        left = max(0, (resized.width - width) // 2)
        top = max(0, (resized.height - height) // 2)
        return resized.crop((left, top, left + width, top + height))

    def _font(self, size: int):
        for path in (
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
        ):
            if Path(path).exists():
                return ImageFont.truetype(path, size=size)
        return ImageFont.load_default()
