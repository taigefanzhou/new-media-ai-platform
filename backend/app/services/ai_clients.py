from __future__ import annotations

import json
import subprocess
import asyncio
import wave
import math
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from uuid import uuid4
import httpx
from app.core.config import get_settings


@dataclass
class GeneratedScript:
    hook: str
    voiceover: str
    storyboard: str
    seedance_prompt: str
    title_options: str
    hashtags: str
    compliance_notes: str
    storyboard_plan: list[dict[str, object]] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


SCRIPT_REALISM_PRESET = {
    "script_style": [
        "少用空泛口号和连续排比，不写明显 AI 腔的万能句",
        "用短句和自然连接词，像公司负责人对镜头讲给客户听",
        "每 12-18 秒必须给一个具体场景、数字、动作或客户问题",
        "避免夸大承诺；收益、成本、效率相关表达必须有条件边界",
    ],
    "talking_head_motion": [
        "natural half-body business talking-head, steady eye contact, relaxed shoulders",
        "small hand gestures only when emphasizing numbers or steps",
        "subtle head movement, occasional blink, natural breathing rhythm",
        "avoid stiff robotic pose, frozen face, exaggerated mouth movement",
    ],
    "face_skin": [
        "realistic facial skin texture, visible pores, natural skin tone",
        "soft office lighting, slight under-eye detail, natural nasolabial folds",
        "not plastic skin, not wax figure, not over-smoothed beauty filter",
    ],
    "voice_style": [
        "Mandarin business speech, calm and credible, medium pace",
        "short pause after key numbers and before conclusions",
        "natural sentence ending, no announcer tone, no mechanical reading",
    ],
}


class ScriptGenerator:
    def __init__(self, model_config=None) -> None:
        self.settings = get_settings()
        self.model_config = model_config

    async def generate(
        self,
        topic: str,
        brand_voice: str,
        duration_seconds: int,
        target_platform: str,
        output_language: str = "zh-CN",
    ) -> GeneratedScript:
        if self.model_config and self.model_config.api_base and self.model_config.api_key:
            return await self._openai_compatible(topic, brand_voice, duration_seconds, target_platform, output_language)
        if self.settings.llm_provider == "stub":
            return self._stub(topic, brand_voice, duration_seconds, target_platform, output_language)
        if self.settings.llm_provider == "openai-compatible":
            return await self._openai_compatible(topic, brand_voice, duration_seconds, target_platform, output_language)
        return self._stub(topic, brand_voice, duration_seconds, target_platform, output_language)

    async def _openai_compatible(
        self,
        topic: str,
        brand_voice: str,
        duration_seconds: int,
        target_platform: str,
        output_language: str = "zh-CN",
    ) -> GeneratedScript:
        api_base = self.model_config.api_base if self.model_config else self.settings.llm_api_base
        api_key = self.model_config.api_key if self.model_config else self.settings.llm_api_key
        model_name = self.model_config.model_name if self.model_config else self.settings.llm_model
        if not api_base or not api_key:
            return self._stub(topic, brand_voice, duration_seconds, target_platform)

        prompt = {
            "topic": topic,
            "brand_voice": brand_voice,
            "duration_seconds": duration_seconds,
            "target_platform": target_platform,
            "output_language": output_language,
            "built_in_realism_preset": SCRIPT_REALISM_PRESET,
            "requirements": [
                "如果 output_language 是 en-US，所有 hook、voiceover、title_options、hashtags、compliance_notes 必须使用英文；否则使用中文",
                "不要复刻或搬运任何参考视频原文",
                "适合公司新媒体账号和数字人口播",
                "默认套用 built_in_realism_preset，让脚本、分镜、口播动作、声音语气和画面提示词都更接近真实实拍",
                "口播稿要像真实负责人表达：先给结论，再讲场景，再讲方案，最后给行动建议",
                "不要使用“赋能、闭环、降本增效、领先、首选”等空泛词，除非能接具体场景或数据边界",
                "严格按 duration_seconds 控制口播长度：30秒约120字中文，60秒约220字中文，180秒约650字中文，360秒约1200字中文",
                "如果 duration_seconds 大于等于60秒，脚本必须是完整连贯结构，不能重复堆砌；按问题、误区、方案、案例、总结推进",
                "storyboard_plan 必须是数组，每段 10-20 秒，180秒至少9段，360秒至少18段",
                "storyboard_plan 每项必须包含：start_second,end_second,shot_type,visual,person_action,screen_text,asset_or_background,ai_prompt,needs_lip_sync",
                "分镜要能真正执行：说明镜头如何动、画面元素如何变化、屏幕文字如何出现；不能只写“继续讲解”",
                "ai_prompt 始终使用英文，适合 Seedance 或其他视频模型；必须包含自然皮肤、真实灯光、非塑料感、非机械感等真实口播要求",
                "seedance_prompt 始终使用英文，必须包含 realistic live-action talking-head style、natural skin texture、natural speech rhythm、no watermark",
                "必须输出严格 JSON",
            ],
            "json_schema": {
                "hook": "开头钩子，一句话",
                "voiceover": "完整口播稿",
                "storyboard": "按镜头分行的分镜",
                "storyboard_plan": [
                    {
                        "start_second": 0,
                        "end_second": 12,
                        "shot_type": "talking_head / b_roll / screen_demo / text_card / process_animation",
                        "visual": "画面内容",
                        "person_action": "人物动作或不露脸说明",
                        "screen_text": "屏幕文字",
                        "asset_or_background": "需要的素材或背景",
                        "ai_prompt": "English prompt for this shot",
                        "needs_lip_sync": True,
                    }
                ],
                "seedance_prompt": "英文视频生成提示词，9:16，专业商务风",
                "title_options": "3个标题，换行分隔",
                "hashtags": "话题标签",
                "compliance_notes": "合规提醒",
            },
        }
        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "你是公司新媒体短视频总编，擅长把选题变成合规、原创、可拍摄的数字人口播脚本。",
                },
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            "temperature": 0.7,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        url = api_base.rstrip("/") + "/chat/completions"

        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        usage = data.get("usage") or {}
        storyboard_plan = self._normalize_storyboard_plan(parsed.get("storyboard_plan"), parsed.get("storyboard", ""), duration_seconds)
        return GeneratedScript(
            hook=parsed.get("hook", ""),
            voiceover=parsed.get("voiceover", ""),
            storyboard=parsed.get("storyboard", ""),
            storyboard_plan=storyboard_plan,
            seedance_prompt=parsed.get("seedance_prompt", ""),
            title_options=parsed.get("title_options", ""),
            hashtags=parsed.get("hashtags", ""),
            compliance_notes=parsed.get("compliance_notes", ""),
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            total_tokens=int(usage.get("total_tokens") or 0),
        )

    def _stub(
        self,
        topic: str,
        brand_voice: str,
        duration_seconds: int,
        target_platform: str,
        output_language: str = "zh-CN",
    ) -> GeneratedScript:
        if output_language == "en-US":
            voiceover = self._stub_voiceover_en(topic, duration_seconds)
            storyboard = self._stub_storyboard_en(topic, duration_seconds)
            storyboard_plan = self._stub_storyboard_plan(topic, duration_seconds, "en-US")
            return GeneratedScript(
                hook=f"The real value of {topic} is not convenience alone, but smarter hotel operations.",
                voiceover=voiceover,
                storyboard=storyboard,
                storyboard_plan=storyboard_plan,
                seedance_prompt=(
                    "Vertical 9:16 long-form business explainer video, consistent modern hotel lobby and guest room, "
                    "smart operations dashboard, realistic live-action talking-head style, natural skin texture, "
                    "relaxed facial expression, natural speech rhythm, smooth transitions, professional lighting, "
                    "continuity across segments, no plastic skin, no robotic pose, no watermark, no third-party logos."
                ),
                title_options=(
                    "1. Smarter Hotel Energy Control\n"
                    "2. No-Card Power Solution for Modern Hotels\n"
                    "3. Better Guest Experience, Lower Energy Waste"
                ),
                hashtags="#HotelTech #SmartHotel #EnergySaving #Hospitality",
                compliance_notes="Use only licensed visuals and verify that all product claims are accurate before publishing.",
            )
        voiceover = self._stub_voiceover_zh(topic, duration_seconds)
        storyboard = self._stub_storyboard_zh(topic, duration_seconds)
        storyboard_plan = self._stub_storyboard_plan(topic, duration_seconds, "zh-CN")
        return GeneratedScript(
            hook=f"你有没有发现，{topic}真正影响结果的不是选择多，而是判断标准。",
            voiceover=voiceover,
            storyboard=storyboard,
            storyboard_plan=storyboard_plan,
            seedance_prompt=(
                "Vertical 9:16 long-form corporate explainer video, consistent presenter and modern business hotel scenes, "
                "clear chapter-like progression, smart operations interface, realistic live-action talking-head style, "
                "natural skin texture, relaxed facial expression, medium speech pace, smooth transitions, professional lighting, "
                "no plastic skin, no robotic pose, no third-party logos, no watermark."
            ),
            title_options=(
                f"1. {topic}怎么选？看这3点\n"
                f"2. 别再盲选{topic}了\n"
                f"3. {topic}的关键判断标准"
            ),
            hashtags=f"#{target_platform} #企业服务 #数字人 #短视频运营",
            compliance_notes="外部素材只可作为选题参考；成片需人工确认无侵权、无夸大承诺。",
        )

    def _stub_voiceover_zh(self, topic: str, duration_seconds: int) -> str:
        sections = [
            f"今天我们完整讲清楚：{topic}。先说结论，真正影响客户判断的不是功能堆得多，而是这个方案能不能解决真实运营问题。",
            "第一段先看场景。很多企业做视频、做获客、做智能化项目时，最容易犯的错，是一开始就讨论工具和价格，却没有把客户旅程、交付边界和后续运营想清楚。",
            "第二段看痛点。客户真正关心的是投入之后有没有效率提升，有没有可量化的数据，有没有更稳定的体验，以及出了问题有没有人负责。",
            "第三段看方案。好的方案应该把前端体验、后台管理、数据记录和持续服务连接起来，让管理者能看见过程，员工能按标准执行，客户能感受到变化。",
            "第四段看落地。不要只讲概念，要把每一步拆成可执行动作：先做需求诊断，再做小范围试点，然后根据真实反馈优化流程，最后再扩大应用。",
            "第五段看风险。任何宣传都不能夸大承诺，也不能把个别案例说成普遍结果。更稳妥的表达，是说明适用条件、实施周期和预期改善方向。",
            "最后总结，真正值得选择的方案，不是看起来最热闹的，而是能持续交付、可复盘、可优化，并且能让客户少走弯路的方案。",
        ]
        target_chars = 120 if duration_seconds <= 30 else 220 if duration_seconds <= 60 else 650 if duration_seconds <= 180 else 1200
        text = ""
        index = 0
        while len(text) < target_chars:
            text = f"{text}{sections[index % len(sections)]}"
            index += 1
            if duration_seconds <= 60 and index >= 3:
                break
        return text[: target_chars + 80]

    def _stub_voiceover_en(self, topic: str, duration_seconds: int) -> str:
        sections = [
            f"Today, let us explain {topic} as a practical business decision, not just a feature list.",
            "First, look at the real operating scenario. A strong solution should reduce friction for users and make daily work easier for the team.",
            "Second, look at measurable value. Decision makers need clearer data, more stable delivery, and a process that can be reviewed after launch.",
            "Third, look at implementation. Start with a small pilot, verify the core workflow, collect feedback, and then expand with a repeatable standard.",
            "Fourth, look at risk control. Claims should be accurate, examples should be authorized, and the final video should avoid exaggerated promises.",
            "In summary, the best solution is the one that can keep delivering value after the first launch.",
        ]
        target_chars = 260 if duration_seconds <= 30 else 520 if duration_seconds <= 60 else 1500 if duration_seconds <= 180 else 2800
        text = ""
        index = 0
        while len(text) < target_chars:
            text = f"{text} {sections[index % len(sections)]}"
            index += 1
            if duration_seconds <= 60 and index >= 3:
                break
        return text.strip()[: target_chars + 120]

    def _stub_storyboard_zh(self, topic: str, duration_seconds: int) -> str:
        return "\n".join(self._storyboard_lines(self._stub_storyboard_plan(topic, duration_seconds, "zh-CN")))

    def _stub_storyboard_en(self, topic: str, duration_seconds: int) -> str:
        return "\n".join(self._storyboard_lines(self._stub_storyboard_plan(topic, duration_seconds, "en-US")))

    def _storyboard_lines(self, plan: list[dict[str, object]]) -> list[str]:
        lines = []
        for index, item in enumerate(plan):
            lines.append(
                f"镜头{index + 1} {item.get('start_second')}-{item.get('end_second')}s："
                f"{item.get('visual')}；屏幕文字：{item.get('screen_text')}。"
            )
        return lines

    def _stub_storyboard_plan(self, topic: str, duration_seconds: int, output_language: str) -> list[dict[str, object]]:
        segment_count = max(4, min(24, math.ceil(max(duration_seconds, 30) / 18)))
        segment_length = math.ceil(duration_seconds / segment_count)
        zh_templates = [
            ("talking_head", "负责人正面对镜开场，背景是现代酒店大堂", "镜头缓慢推进，底部出现身份条", "开场钩子"),
            ("text_card", "传统房卡取电痛点以三张卡片弹出", "卡片逐条滑入，突出补卡、空调空转、房态不透明", "运营痛点"),
            ("process_animation", "订单、门锁、人在状态、客控形成联动流程", "节点连线亮起，展示数据流动", "状态联动"),
            ("b_roll", "客人进入房间，灯光和空调自动进入欢迎模式", "用真实酒店房间感镜头表现舒适体验", "住客体验"),
            ("screen_demo", "后台能耗和房态看板动态变化", "展示异常提醒和房态更新", "管理看得见"),
            ("text_card", "节能、效率、风控三个价值点并列出现", "数字标签依次放大", "经营价值"),
            ("process_animation", "退房、清洁、维修工单自动流转", "流程线从左到右推进", "工单闭环"),
            ("talking_head", "负责人给出三阶段落地建议", "镜头稳定，旁边出现阶段清单", "落地路径"),
            ("talking_head", "总结无卡取电是智慧客房入口", "缓慢拉远，品牌式收尾", "总结"),
        ]
        en_templates = [
            ("talking_head", "Presenter opens in a modern hotel lobby", "slow push-in, lower third appears", "Opening hook"),
            ("text_card", "Three pain-point cards about key cards and energy waste", "cards slide in one by one", "Pain points"),
            ("process_animation", "Booking, lock, occupancy and room control nodes connect", "animated data-flow lines", "Connected states"),
            ("b_roll", "Guest enters a smart hotel room with lights and AC ready", "realistic hospitality scene", "Guest experience"),
            ("screen_demo", "Operations dashboard shows energy and room status", "alerts and charts animate", "Visible operations"),
            ("text_card", "Energy saving, efficiency and risk control value cards", "numbers scale up", "Business value"),
            ("process_animation", "Checkout, cleaning and maintenance workflow closes the loop", "left-to-right process animation", "Workflow"),
            ("talking_head", "Presenter explains three-stage rollout", "stable shot with checklist", "Rollout"),
            ("talking_head", "Conclusion that cardless power is the smart-room entry point", "slow pullback ending", "Summary"),
        ]
        templates = en_templates if output_language == "en-US" else zh_templates
        plan: list[dict[str, object]] = []
        for index in range(segment_count):
            start = index * segment_length
            end = min(duration_seconds, (index + 1) * segment_length)
            shot_type, visual, action, screen_text = templates[min(index, len(templates) - 1)]
            plan.append(
                {
                    "start_second": start,
                    "end_second": end,
                    "shot_type": shot_type,
                    "visual": f"{visual}，围绕“{topic}”推进第{index + 1}段内容",
                    "person_action": action,
                    "screen_text": screen_text,
                    "asset_or_background": "modern business hotel, guest room, smart room control dashboard",
                    "ai_prompt": (
                        f"Vertical 9:16 realistic business hotel video, {shot_type}, {visual}, "
                        f"topic: {topic}, natural skin texture, relaxed facial expression, medium speech pace, "
                        "smooth motion, clean subtitles, professional lighting, no plastic skin, no robotic pose, no watermark"
                    ),
                    "needs_lip_sync": shot_type == "talking_head",
                }
            )
        return plan

    def _normalize_storyboard_plan(self, raw_plan, storyboard: str, duration_seconds: int) -> list[dict[str, object]]:
        if isinstance(raw_plan, str):
            try:
                raw_plan = json.loads(raw_plan)
            except json.JSONDecodeError:
                raw_plan = None
        if not isinstance(raw_plan, list):
            return self._plan_from_storyboard_lines(storyboard, duration_seconds)
        normalized = []
        for index, item in enumerate(raw_plan):
            if not isinstance(item, dict):
                continue
            start = int(item.get("start_second") or item.get("start") or index * 10)
            end = int(item.get("end_second") or item.get("end") or min(duration_seconds, start + 10))
            normalized.append(
                {
                    "start_second": max(0, start),
                    "end_second": min(duration_seconds, max(end, start + 1)),
                    "shot_type": str(item.get("shot_type") or "talking_head"),
                    "visual": str(item.get("visual") or item.get("description") or ""),
                    "person_action": str(item.get("person_action") or ""),
                    "screen_text": str(item.get("screen_text") or ""),
                    "asset_or_background": str(item.get("asset_or_background") or ""),
                    "ai_prompt": str(item.get("ai_prompt") or item.get("prompt") or ""),
                    "needs_lip_sync": bool(item.get("needs_lip_sync", item.get("shot_type") == "talking_head")),
                }
            )
        return normalized or self._plan_from_storyboard_lines(storyboard, duration_seconds)

    def _plan_from_storyboard_lines(self, storyboard: str, duration_seconds: int) -> list[dict[str, object]]:
        lines = [line.strip() for line in storyboard.splitlines() if line.strip()]
        if not lines:
            return self._stub_storyboard_plan("视频主题", duration_seconds, "zh-CN")
        segment_length = max(1, math.ceil(duration_seconds / len(lines)))
        plan = []
        for index, line in enumerate(lines):
            start = index * segment_length
            end = min(duration_seconds, (index + 1) * segment_length)
            plan.append(
                {
                    "start_second": start,
                    "end_second": end,
                    "shot_type": "talking_head" if index in (0, len(lines) - 1) else "text_card",
                    "visual": line,
                    "person_action": "根据口播自然讲解，画面需要有轻微镜头运动",
                    "screen_text": line[:18],
                    "asset_or_background": "business hotel scene",
                    "ai_prompt": f"Vertical 9:16 realistic business hotel video, {line}, smooth camera motion, no watermark",
                    "needs_lip_sync": index in (0, len(lines) - 1),
                }
            )
        return plan

    def _script_segment_count(self, duration_seconds: int) -> int:
        return max(4, min(36, math.ceil(max(duration_seconds, 30) / 10)))


class MediaGenerationClient:
    def __init__(
        self,
        video_model_config=None,
        tts_model_config=None,
        digital_human_model_config=None,
        storage_dir: str | Path | None = None,
    ) -> None:
        self.settings = get_settings()
        self.video_model_config = video_model_config
        self.tts_model_config = tts_model_config
        self.digital_human_model_config = digital_human_model_config
        self.storage_dir = Path(storage_dir or self.settings.storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    async def synthesize_voice(self, text: str, voice: Optional[str] = None) -> str:
        api_base = self.tts_model_config.api_base if self.tts_model_config and self.tts_model_config.api_base else self.settings.tts_api_base
        api_key = self.tts_model_config.api_key if self.tts_model_config and self.tts_model_config.api_key else self.settings.tts_api_key
        provider = self.tts_model_config.provider if self.tts_model_config else self.settings.tts_provider
        default_voice = self.tts_model_config.model_name if self.tts_model_config else self.settings.tts_voice
        if provider == "mock" or not api_base:
            return self._local_voiceover(text, voice)

        payload = {
            "text": text,
            "voice": voice or default_voice,
            "provider": provider,
            "format": "wav",
        }
        data = await self._post_media(
            api_base,
            "/synthesize",
            payload,
            api_key=api_key,
            binary=True,
        )
        output_path = self._asset_path("voice", "voiceover.wav")
        output_path.write_bytes(data)
        return str(output_path)

    async def clone_voice_from_source_video(
        self,
        source_video_path: str,
        speaker_name: str,
        model_config=None,
    ) -> str:
        api_base = model_config.api_base if model_config and model_config.api_base else self.settings.voice_clone_api_base
        api_key = model_config.api_key if model_config and model_config.api_key else self.settings.voice_clone_api_key
        provider = model_config.provider if model_config else self.settings.voice_clone_provider
        if not api_base or not api_key:
            raise RuntimeError("Voice clone service is not configured")

        headers = {"Authorization": f"Bearer {api_key}"}
        data = {
            "provider": provider,
            "speaker_name": speaker_name,
        }
        with open(source_video_path, "rb") as source_file:
            files = {
                "source_video": (Path(source_video_path).name, source_file, "video/mp4"),
            }
            async with httpx.AsyncClient(timeout=900) as client:
                response = await client.post(api_base.rstrip("/") + "/clone", data=data, files=files, headers=headers)
                response.raise_for_status()
                result = response.json()
        voice_id = self._extract_voice_id(result)
        if not voice_id:
            raise RuntimeError("Voice clone service did not return a voice_id")
        return voice_id

    async def generate_talking_avatar(
        self,
        portrait_path: Optional[str],
        audio_path: str,
        source_video_path: Optional[str] = None,
        style_prompt: str = "",
    ) -> str:
        api_base = (
            self.digital_human_model_config.api_base
            if self.digital_human_model_config and self.digital_human_model_config.api_base
            else self.settings.digital_human_api_base
        )
        api_key = (
            self.digital_human_model_config.api_key
            if self.digital_human_model_config and self.digital_human_model_config.api_key
            else self.settings.digital_human_api_key
        )
        provider = (
            self.digital_human_model_config.provider
            if self.digital_human_model_config
            else self.settings.digital_human_provider
        )
        if provider == "mock" or not api_base:
            if portrait_path and self._is_local_path(audio_path):
                return self._local_talking_avatar_preview(portrait_path, audio_path)
            return self._mock_asset("digital-human", "talking-avatar.mp4")

        if self._is_local_path(audio_path) and (
            self._is_local_path(portrait_path or "") or self._is_local_path(source_video_path or "")
        ):
            result = await self._post_digital_human_media(
                portrait_path,
                audio_path,
                source_video_path,
                api_base,
                api_key,
                provider,
                style_prompt,
            )
            media_url = self._extract_media_url(result, "digital_human_video")
            if media_url.startswith("http"):
                return await self._download_media(media_url, "digital-human", "talking-avatar.mp4")
            return media_url

        payload = {
            "provider": provider,
            "portrait_path": portrait_path,
            "audio_path": audio_path,
            "source_video_path": source_video_path,
            "format": "mp4",
            "style_prompt": style_prompt,
            "motion_prompt": ", ".join(SCRIPT_REALISM_PRESET["talking_head_motion"]),
            "voice_style": ", ".join(SCRIPT_REALISM_PRESET["voice_style"]),
        }
        result = await self._post_media(
            api_base,
            "/generate",
            payload,
            api_key=api_key,
        )
        return self._extract_media_url(result, "digital_human_video")

    def can_generate_talking_avatar(self) -> bool:
        api_base = (
            self.digital_human_model_config.api_base
            if self.digital_human_model_config and self.digital_human_model_config.api_base
            else self.settings.digital_human_api_base
        )
        provider = (
            self.digital_human_model_config.provider
            if self.digital_human_model_config
            else self.settings.digital_human_provider
        )
        return bool(api_base) and provider != "mock"

    async def generate_seedance_clips(self, prompt: str, duration_seconds: int = 30) -> list[str]:
        plan = self.segment_plan(prompt, "", duration_seconds)
        return [
            await self.generate_video_segment(item["prompt"], item["duration_seconds"], index, len(plan))
            for index, item in enumerate(plan)
        ]

    async def generate_video_segment(
        self,
        prompt: str,
        duration_seconds: int,
        index: int,
        total: int,
    ) -> str:
        if self.video_model_config and self.video_model_config.provider == "seedance":
            return await self._generate_seedance_clip_via_ark(
                self._segment_prompt(prompt, index, total),
                duration_seconds,
            )

        provider = self.settings.video_generation_provider
        if provider == "seedance" and self.settings.seedance_api_base:
            return await self._generate_seedance_clip_via_ark(
                self._segment_prompt(prompt, index, total),
                duration_seconds,
            )

        if provider == "comfyui" and self.settings.comfyui_api_base:
            payload = {
                "prompt": prompt,
                "duration_seconds": duration_seconds,
                "segment_index": index + 1,
                "segment_count": total,
                "workflow": "default-video-generation",
            }
            result = await self._post_media(self.settings.comfyui_api_base, "/prompt", payload)
            return self._extract_media_url(result, "comfyui_job")

        return self._mock_asset("seedance", f"clip-{index + 1}.mp4")

    def segment_plan(
        self,
        prompt: str,
        storyboard: str,
        duration_seconds: int = 30,
        storyboard_plan: str | list[dict[str, object]] | None = None,
    ) -> list[dict[str, object]]:
        structured_plan = self._media_storyboard_plan(storyboard_plan, duration_seconds)
        if structured_plan:
            return structured_plan
        clip_count = self._clip_count_for_duration(duration_seconds)
        clip_duration = self._clip_duration_for_duration(duration_seconds)
        storyboard_lines = [line.strip() for line in storyboard.splitlines() if line.strip()]
        plan: list[dict[str, object]] = []
        for index in range(clip_count):
            start = index * clip_duration
            remaining = max(clip_duration, duration_seconds - start)
            item_duration = min(clip_duration, remaining)
            storyboard_hint = storyboard_lines[index] if index < len(storyboard_lines) else ""
            segment_prompt = (
                f"{prompt.strip()}\n"
                f"Segment brief: {storyboard_hint or f'continue chapter {index + 1} with clear visual continuity'}"
            )
            plan.append(
                {
                    "title": f"第 {index + 1} 段",
                    "duration_seconds": int(item_duration),
                    "prompt": segment_prompt,
                }
            )
        return plan

    def _media_storyboard_plan(
        self,
        storyboard_plan: str | list[dict[str, object]] | None,
        duration_seconds: int,
    ) -> list[dict[str, object]]:
        if isinstance(storyboard_plan, str) and storyboard_plan.strip():
            try:
                storyboard_plan = json.loads(storyboard_plan)
            except json.JSONDecodeError:
                storyboard_plan = None
        if not isinstance(storyboard_plan, list):
            return []
        plan: list[dict[str, object]] = []
        for index, item in enumerate(storyboard_plan):
            if not isinstance(item, dict):
                continue
            start = int(item.get("start_second") or index * 10)
            end = int(item.get("end_second") or min(duration_seconds, start + self._clip_duration_for_duration(duration_seconds)))
            item_duration = max(1, min(duration_seconds, end) - start)
            prompt = item.get("ai_prompt") or item.get("visual") or item.get("screen_text") or ""
            plan.append(
                {
                    "title": str(item.get("screen_text") or item.get("shot_type") or f"第 {index + 1} 段"),
                    "start_second": int(start),
                    "duration_seconds": int(item_duration),
                    "prompt": str(prompt),
                    "shot_type": str(item.get("shot_type") or ""),
                    "visual": str(item.get("visual") or ""),
                    "person_action": str(item.get("person_action") or ""),
                    "screen_text": str(item.get("screen_text") or ""),
                    "asset_or_background": str(item.get("asset_or_background") or ""),
                    "needs_lip_sync": bool(item.get("needs_lip_sync", False)),
                }
            )
        return plan

    async def compose_final_video(self, clips: list[str], avatar_clip: str) -> str:
        if self.settings.composition_provider != "ffmpeg":
            if self._is_local_path(avatar_clip):
                return avatar_clip
            local_clip = next((item for item in clips if self._is_local_path(item)), None)
            if local_clip:
                return local_clip
            return self._mock_asset("final", "final-video.mp4")

        local_inputs = [item for item in [avatar_clip, *clips] if self._is_local_path(item)]
        if not local_inputs:
            return self._mock_asset("final", "final-video.mp4")

        list_path = self._asset_path("composition", "inputs.txt")
        output_path = self._asset_path("final", "final-video.mp4")
        list_path.write_text(
            "\n".join(f"file '{Path(path).resolve()}'" for path in local_inputs),
            encoding="utf-8",
        )
        command = [
            self.settings.ffmpeg_binary,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c",
            "copy",
            str(output_path),
        ]
        subprocess.run(command, check=True, capture_output=True)
        return str(output_path)

    async def compose_scene_video(
        self,
        clips: list[str],
        audio_path: Optional[str] = None,
    ) -> str:
        from moviepy.editor import AudioFileClip, VideoFileClip, concatenate_videoclips
        from PIL import Image

        local_inputs = [item for item in clips if self._is_local_path(item) and Path(item).exists()]
        if not local_inputs:
            return self._mock_asset("final", "seedance-scene.mp4")

        if not hasattr(Image, "ANTIALIAS"):
            Image.ANTIALIAS = Image.Resampling.LANCZOS
        output_path = self._asset_path("final", "seedance-scene.mp4")
        target_width, target_height = 720, 1280
        scene_clips = []
        audio = None
        final_clip = None
        try:
            for path in local_inputs:
                clip = VideoFileClip(path).without_audio()
                scale = max(target_width / clip.w, target_height / clip.h)
                clip = clip.resize(scale)
                clip = clip.crop(
                    x_center=clip.w / 2,
                    y_center=clip.h / 2,
                    width=target_width,
                    height=target_height,
                )
                scene_clips.append(clip)

            final_clip = concatenate_videoclips(scene_clips, method="compose")
            if audio_path and self._is_local_path(audio_path) and Path(audio_path).exists():
                audio = AudioFileClip(audio_path)
                final_clip = final_clip.set_audio(audio.subclip(0, min(audio.duration, final_clip.duration)))
            final_clip.write_videofile(
                str(output_path),
                fps=24,
                codec="libx264",
                audio_codec="aac",
                preset="medium",
                bitrate="3500k",
                threads=4,
                verbose=False,
                logger=None,
            )
        finally:
            if final_clip is not None:
                final_clip.close()
            if audio is not None:
                audio.close()
            for clip in scene_clips:
                clip.close()
        return str(output_path)

    async def compose_talking_head_template(
        self,
        talking_clip_path: str,
        voiceover: str,
        storyboard_plan: str | list[dict[str, object]] | None,
        title: str,
        speaker_name: str,
        speaker_role: str,
        duration_seconds: int = 60,
        audio_path: Optional[str] = None,
    ) -> str:
        from moviepy.editor import AudioFileClip, VideoClip, VideoFileClip
        from PIL import Image, ImageDraw, ImageFilter
        import numpy as np

        if not self._is_local_path(talking_clip_path) or not Path(talking_clip_path).exists():
            raise RuntimeError("Digital human talking video was not generated")

        talking_clip = VideoFileClip(talking_clip_path)
        external_audio = None
        duration = min(max(talking_clip.duration, 6), max(duration_seconds, 6))
        if talking_clip.audio is None and audio_path and self._is_local_path(audio_path) and Path(audio_path).exists():
            external_audio = AudioFileClip(audio_path)
            duration = min(duration, external_audio.duration)

        output_path = self._asset_path("final", "talking-head-template.mp4")
        frame_size = (720, 1280)
        top_h = 238
        bottom_y = 1064
        main_h = bottom_y - top_h
        bg_color = (9, 38, 54)
        yellow = (238, 190, 72)
        white = (248, 250, 252)
        title_font = self._load_font(42)
        title_font_small = self._load_font(36)
        subtitle_font = self._load_font(34)
        meta_font = self._load_font(24)
        small_font = self._load_font(20)
        card_title_font = self._load_font(38)
        card_body_font = self._load_font(25)
        title_lines = self._template_title_lines(title or "公司方案讲解")
        subtitles = self._subtitle_events(voiceover, duration)
        cards = self._template_card_segments(storyboard_plan, duration)

        def video_image(t: float, size: tuple[int, int]) -> Image.Image:
            frame = talking_clip.get_frame(min(t, talking_clip.duration - 0.05))
            image = Image.fromarray(frame).convert("RGB")
            scale = max(size[0] / image.width, size[1] / image.height)
            resized = image.resize((int(image.width * scale), int(image.height * scale)), Image.Resampling.LANCZOS)
            x = max(0, (resized.width - size[0]) // 2)
            y = max(0, (resized.height - size[1]) // 2)
            return resized.crop((x, y, x + size[0], y + size[1]))

        def card_for_time(t: float) -> dict[str, object] | None:
            for card in cards:
                start = float(card.get("start_second", 0))
                end = start + float(card.get("duration_seconds", 5))
                if start <= t < end:
                    return card
            return None

        def wrap_text(text: str, limit: int, max_lines: int) -> list[str]:
            text = str(text or "").replace("\n", " ").strip()
            lines: list[str] = []
            current = ""
            for char in text:
                current += char
                if len(current) >= limit:
                    lines.append(current)
                    current = ""
            if current:
                lines.append(current)
            return lines[:max_lines]

        def subtitle_for_time(t: float) -> str:
            for start, end, text in subtitles:
                if start <= t < end:
                    return text
            return ""

        def draw_shadow_text(draw, xy, text, font, fill, shadow=(0, 0, 0, 160), stroke=2):
            x, y = xy
            draw.text((x + 2, y + 3), text, font=font, fill=shadow, stroke_width=stroke, stroke_fill=shadow)
            draw.text((x, y), text, font=font, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0, 120))

        def draw_centered(draw, text, y, font, fill, stroke_width=0):
            bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
            x = (frame_size[0] - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), text, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=(0, 0, 0, 150))

        def draw_template_chrome(draw):
            draw.rectangle((0, 0, frame_size[0], top_h), fill=bg_color)
            draw.rectangle((0, bottom_y, frame_size[0], frame_size[1]), fill=bg_color)
            draw_centered(draw, title_lines[0], 70, title_font if len(title_lines[0]) <= 14 else title_font_small, white, 2)
            draw_centered(draw, title_lines[1], 132, title_font if len(title_lines[1]) <= 14 else title_font_small, yellow, 2)
            draw.text((50, 1130), "AI\n生\n成", font=small_font, fill=(148, 163, 184, 190), spacing=6)
            draw.text((238, 1120), speaker_name or "数字人", font=self._load_font(38), fill=white)
            draw.line((330, 1118, 330, 1192), fill=(226, 232, 240, 210), width=2)
            for index, line in enumerate(wrap_text(speaker_role or "品牌顾问", 15, 3)):
                draw.text((352, 1116 + index * 28), line, font=meta_font, fill=white)

        def draw_subtitle(draw, text: str):
            lines = wrap_text(text, 15, 2)
            y = 908 if len(lines) == 1 else 875
            for line in lines:
                bbox = draw.textbbox((0, 0), line, font=subtitle_font, stroke_width=2)
                x = (frame_size[0] - (bbox[2] - bbox[0])) // 2
                draw_shadow_text(draw, (x, y), line, subtitle_font, white)
                y += 44

        def draw_card(canvas: Image.Image, draw, card: dict[str, object], t: float):
            card_bg = Image.new("RGB", (720, main_h), (222, 244, 247))
            bg_draw = ImageDraw.Draw(card_bg)
            for i in range(10):
                y = 80 + i * 70 + int(6 * math.sin(t * 0.8 + i))
                bg_draw.line((90, y, 630, y + 28), fill=(164, 213, 220), width=2)
            bg_draw.rounded_rectangle((94, 108, 626, 590), radius=24, fill=(248, 252, 252), outline=(185, 220, 225), width=2)
            screen_text = str(card.get("title") or card.get("screen_text") or "方案要点")
            visual = str(card.get("visual") or card.get("prompt") or "")
            draw_center = ImageDraw.Draw(card_bg)
            for idx, line in enumerate(wrap_text(screen_text, 12, 2)):
                bbox = draw_center.textbbox((0, 0), line, font=card_title_font)
                draw_center.text(((720 - (bbox[2] - bbox[0])) // 2, 238 + idx * 48), line, font=card_title_font, fill=(15, 23, 42))
            bg_draw.line((236, 360, 484, 360), fill=(15, 118, 110), width=3)
            for idx, line in enumerate(wrap_text(visual, 18, 3)):
                bbox = draw_center.textbbox((0, 0), line, font=card_body_font)
                draw_center.text(((720 - (bbox[2] - bbox[0])) // 2, 392 + idx * 36), line, font=card_body_font, fill=(51, 65, 85))

            mini = video_image(t, (160, 270)).filter(ImageFilter.UnsharpMask(radius=1, percent=110, threshold=3))
            card_bg.paste(mini, (52, main_h - 300))
            canvas.paste(card_bg, (0, top_h))
            draw.rectangle((0, top_h, 720, bottom_y), outline=(255, 255, 255, 30), width=1)

        def make_frame(t: float):
            canvas = Image.new("RGB", frame_size, bg_color).convert("RGBA")
            card = card_for_time(t)
            draw = ImageDraw.Draw(canvas)
            if card:
                draw_card(canvas, draw, card, t)
            else:
                main = video_image(t, (720, main_h))
                canvas.paste(main, (0, top_h))
            overlay = Image.new("RGBA", frame_size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            overlay_draw.rectangle((0, bottom_y - 92, 720, bottom_y), fill=(0, 0, 0, 45))
            canvas = Image.alpha_composite(canvas, overlay)
            draw = ImageDraw.Draw(canvas)
            draw_template_chrome(draw)
            draw_subtitle(draw, subtitle_for_time(t))
            return np.array(canvas.convert("RGB"))

        try:
            clip = VideoClip(make_frame, duration=duration)
            audio = talking_clip.audio or external_audio
            if audio is not None:
                clip = clip.set_audio(audio.subclip(0, min(audio.duration, duration)))
            clip.write_videofile(
                str(output_path),
                fps=24,
                codec="libx264",
                audio_codec="aac",
                preset="medium",
                bitrate="4200k",
                threads=4,
                verbose=False,
                logger=None,
            )
            clip.close()
        finally:
            talking_clip.close()
            if external_audio is not None:
                external_audio.close()
        return str(output_path)

    async def compose_dynamic_explainer(
        self,
        voiceover: str,
        storyboard_plan: str | list[dict[str, object]] | None,
        audio_path: str,
        portrait_path: Optional[str] = None,
        duration_seconds: int = 30,
    ) -> str:
        from moviepy.editor import AudioFileClip, VideoClip
        from PIL import Image, ImageDraw, ImageFilter
        import numpy as np

        audio = AudioFileClip(audio_path)
        duration = min(max(audio.duration, 6), max(duration_seconds, 6))
        plan = self._media_storyboard_plan(storyboard_plan, int(duration)) or self.segment_plan(
            "dynamic explainer",
            "",
            int(duration),
        )
        output_path = self._asset_path("final", "dynamic-explainer.mp4")
        frame_size = (720, 1280)
        title_font = self._load_font(38)
        body_font = self._load_font(26)
        small_font = self._load_font(19)
        subtitle_font = self._load_font(30)
        portrait = None
        if portrait_path and self._is_local_path(portrait_path) and Path(portrait_path).exists():
            portrait = Image.open(portrait_path).convert("RGB")
            side = min(portrait.size)
            portrait = portrait.crop(
                (
                    (portrait.width - side) // 2,
                    (portrait.height - side) // 2,
                    (portrait.width - side) // 2 + side,
                    (portrait.height - side) // 2 + side,
                )
            )

        subtitles = self._subtitle_events(voiceover, duration)
        palette = [
            ((16, 74, 95), (15, 118, 110)),
            ((40, 45, 72), (220, 95, 55)),
            ((19, 70, 95), (37, 99, 235)),
            ((49, 70, 52), (22, 163, 74)),
            ((74, 55, 24), (245, 158, 11)),
            ((39, 45, 84), (124, 58, 237)),
        ]

        def scene_for_time(t: float) -> tuple[int, dict[str, object]]:
            for index, item in enumerate(plan):
                start = float(item.get("start_second", index * 10))
                end = start + float(item.get("duration_seconds", 10))
                if start <= t < end:
                    return index, item
            return len(plan) - 1, plan[-1]

        def subtitle_for_time(t: float) -> str:
            for start, end, text in subtitles:
                if start <= t < end:
                    return text
            return subtitles[-1][2] if subtitles else ""

        def draw_round(draw, box, radius, fill, outline=None, width=1):
            draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)

        def paste_round(base, image, xy, radius):
            mask = Image.new("L", image.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, image.width, image.height), radius=radius, fill=255)
            base.paste(image, xy, mask)

        def wrap_text(text: str, limit: int, max_lines: int) -> list[str]:
            lines: list[str] = []
            current = ""
            for char in text:
                current += char
                if len(current) >= limit:
                    lines.append(current)
                    current = ""
            if current:
                lines.append(current)
            return lines[:max_lines]

        def make_frame(t: float):
            index, scene = scene_for_time(t)
            bg_rgb, accent_rgb = palette[index % len(palette)]
            width, height = frame_size
            base = Image.new("RGB", frame_size, bg_rgb)
            arr = np.array(base).astype(np.float32)
            yy = np.linspace(0, 1, height)[:, None]
            xx = np.linspace(0, 1, width)[None, :]
            glow = (np.sin(xx * 5 + t * 0.08) + np.cos(yy * 4 - t * 0.06)) * 18
            arr[..., 0] = np.clip(arr[..., 0] + glow + yy * 28, 0, 255)
            arr[..., 1] = np.clip(arr[..., 1] + glow * 0.4 + xx * 20, 0, 255)
            arr[..., 2] = np.clip(arr[..., 2] + 38 * (1 - yy), 0, 255)
            canvas = Image.fromarray(arr.astype(np.uint8)).convert("RGBA")
            draw = ImageDraw.Draw(canvas)

            for row in range(8):
                y = 80 + row * 130 + int(18 * math.sin(t * 0.22 + row))
                x = -100 + ((t * 22 + row * 97) % (width + 200))
                draw.line((x, y, x + 260, y + 40), fill=(255, 255, 255, 22), width=2)

            draw_round(draw, (38, 32, 682, 106), 24, (255, 255, 255, 32), (255, 255, 255, 42))
            draw.text((64, 48), f"镜头 {index + 1:02d}", font=small_font, fill=(205, 236, 255, 235))
            draw_round(draw, (246, 60, 650, 72), 999, (255, 255, 255, 45))
            draw_round(draw, (246, 60, 246 + int(404 * t / duration), 72), 999, (*accent_rgb, 235))
            draw.text((574, 78), f"{int(t // 60):02d}:{int(t % 60):02d}", font=small_font, fill=(226, 232, 240, 230))

            if portrait:
                draw_round(draw, (64, 136, 656, 638), 42, (255, 255, 255, 28), (255, 255, 255, 48))
                scale = 1.04 + 0.04 * math.sin(t * 0.16)
                size = int(500 * scale)
                face = portrait.resize((size, size), Image.Resampling.LANCZOS)
                crop_x = max(0, (face.width - 500) // 2 + int(12 * math.sin(t * 0.11)))
                crop_y = max(0, (face.height - 500) // 2 + int(8 * math.cos(t * 0.13)))
                face = face.crop((crop_x, crop_y, crop_x + 500, crop_y + 500)).filter(
                    ImageFilter.UnsharpMask(radius=1, percent=110, threshold=3)
                )
                paste_round(canvas, face, (110, 148 + int(4 * math.sin(t * 0.35))), 34)
                draw_round(draw, (86, 575, 634, 622), 18, (2, 6, 23, 155))
                draw.text((112, 588), "数字人讲解画面 · 动态镜头", font=small_font, fill=(255, 255, 255, 232))
                for bar in range(22):
                    bar_height = int(6 + 20 * abs(math.sin(t * 3 + bar * 0.55)))
                    x = 458 + bar * 6
                    draw.rounded_rectangle(
                        (x, 599 - bar_height // 2, x + 3, 599 + bar_height // 2),
                        radius=2,
                        fill=(*accent_rgb, 230),
                    )

            visual = str(scene.get("visual") or scene.get("title") or "动态讲解")
            screen_text = str(scene.get("screen_text") or visual[:18])
            draw_round(draw, (46, 668, 674, 820), 26, (255, 255, 255, 238))
            draw.text((76, 696), screen_text[:24], font=title_font, fill=(20, 29, 43, 255))
            draw.line((76, 756, 644, 756), fill=(*accent_rgb, 180), width=4)
            for line_index, line in enumerate(wrap_text(visual, 22, 2)):
                draw.text((76, 776 + line_index * 32), line, font=small_font, fill=(71, 85, 105, 255))

            items = [
                str(scene.get("shot_type") or "dynamic"),
                str(scene.get("asset_or_background") or "hotel scene"),
                "字幕与卖点卡片同步",
            ]
            for item_index, item in enumerate(items):
                y = 858 + item_index * 78
                draw_round(draw, (54, y, 666, y + 58), 18, (255, 255, 255, 218), (255, 255, 255, 90))
                draw.ellipse((82, y + 18, 106, y + 42), fill=(*accent_rgb, 235))
                draw.text((126, y + 15), item[:28], font=body_font, fill=(23, 37, 52, 255))

            draw_round(draw, (36, 1128, 684, 1250), 24, (2, 6, 23, 185))
            for line_index, line in enumerate(wrap_text(subtitle_for_time(t), 18, 3)):
                draw.text((66, 1152 + line_index * 38), line, font=subtitle_font, fill=(255, 255, 255, 245))

            return np.array(canvas.convert("RGB"))

        clip = VideoClip(make_frame, duration=duration).set_audio(audio.subclip(0, duration))
        clip.write_videofile(
            str(output_path),
            fps=20,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            bitrate="2800k",
            threads=4,
            verbose=False,
            logger=None,
        )
        audio.close()
        clip.close()
        return str(output_path)

    async def _post_digital_human_media(
        self,
        portrait_path: Optional[str],
        audio_path: str,
        source_video_path: Optional[str] = None,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        provider: Optional[str] = None,
        style_prompt: str = "",
    ) -> dict[str, object]:
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if not api_base:
            raise RuntimeError("Digital human service is not configured")
        url = api_base.rstrip("/") + "/generate"
        data = {
            "provider": provider or self.settings.digital_human_provider,
            "format": "mp4",
            "style_prompt": style_prompt,
            "motion_prompt": ", ".join(SCRIPT_REALISM_PRESET["talking_head_motion"]),
            "face_skin_prompt": ", ".join(SCRIPT_REALISM_PRESET["face_skin"]),
            "voice_style": ", ".join(SCRIPT_REALISM_PRESET["voice_style"]),
        }
        with open(audio_path, "rb") as audio_file:
            files = {
                "audio": (Path(audio_path).name, audio_file, "audio/wav"),
            }
            if portrait_path and self._is_local_path(portrait_path):
                with open(portrait_path, "rb") as portrait_file:
                    files["portrait"] = (Path(portrait_path).name, portrait_file, "image/jpeg")
                    if source_video_path and self._is_local_path(source_video_path):
                        with open(source_video_path, "rb") as source_video_file:
                            files["source_video"] = (Path(source_video_path).name, source_video_file, "video/mp4")
                            return await self._submit_digital_human_request(url, data, files, headers)
                    return await self._submit_digital_human_request(url, data, files, headers)
            if source_video_path and self._is_local_path(source_video_path):
                with open(source_video_path, "rb") as source_video_file:
                    files["source_video"] = (Path(source_video_path).name, source_video_file, "video/mp4")
                    return await self._submit_digital_human_request(url, data, files, headers)
            return await self._submit_digital_human_request(url, data, files, headers)

    async def _submit_digital_human_request(
        self,
        url: str,
        data: dict[str, object],
        files: dict[str, object],
        headers: dict[str, str],
    ) -> dict[str, object]:
        async with httpx.AsyncClient(timeout=900) as client:
            response = await client.post(url, data=data, files=files, headers=headers)
            response.raise_for_status()
            if response.headers.get("content-type", "").startswith("video/"):
                output_path = self._asset_path("digital-human", "talking-avatar.mp4")
                output_path.write_bytes(response.content)
                return {"path": str(output_path)}
            return response.json()

    async def _post_media(
        self,
        base_url: str,
        path: str,
        payload: dict[str, object],
        api_key: Optional[str] = None,
        binary: bool = False,
    ):
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        url = base_url.rstrip("/") + path
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            if binary:
                return response.content
            return response.json()

    async def _generate_seedance_clip_via_ark(self, prompt: str, duration_seconds: int = 5) -> str:
        config = self.video_model_config
        api_base = config.api_base if config and config.api_base else self.settings.seedance_api_base
        api_key = config.api_key if config and config.api_key else self.settings.seedance_api_key
        model_name = config.model_name if config and config.model_name else self.settings.seedance_model
        if not api_base:
            api_base = "https://ark.cn-beijing.volces.com/api/v3"
        if not api_key:
            return self._mock_asset("seedance", "clip-1.mp4")

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model_name,
            "content": [{"type": "text", "text": self._seedance_prompt(prompt, duration_seconds)}],
        }
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(
                api_base.rstrip("/") + "/contents/generations/tasks",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            task_id = response.json().get("id")
            if not task_id:
                raise RuntimeError("Seedance task id not returned")

            task_data = None
            query_url = api_base.rstrip("/") + f"/contents/generations/tasks/{task_id}"
            for _ in range(120):
                await asyncio.sleep(5)
                task_response = await client.get(query_url, headers=headers)
                task_response.raise_for_status()
                task_data = task_response.json()
                status = task_data.get("status")
                if status == "succeeded":
                    break
                if status in {"failed", "cancelled", "canceled"}:
                    raise RuntimeError(f"Seedance task {status}: {task_data.get('error')}")
            else:
                raise RuntimeError(f"Seedance task timed out: {task_id}")

            video_url = self._seedance_video_url(task_data or {})
            if not video_url:
                raise RuntimeError("Seedance video url not returned")
            video_response = await client.get(video_url, timeout=180)
            video_response.raise_for_status()

        output_path = self._asset_path("seedance", f"{task_id}.mp4")
        output_path.write_bytes(video_response.content)
        return str(output_path)

    async def _download_media(self, url: str, category: str, filename: str) -> str:
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.get(url)
            response.raise_for_status()
        output_path = self._asset_path(category, filename)
        output_path.write_bytes(response.content)
        return str(output_path)

    def _local_voiceover(self, text: str, voice: Optional[str] = None) -> str:
        output_path = self._asset_path("voice", "voiceover.aiff")
        say_binary = "/usr/bin/say"
        if Path(say_binary).exists():
            command = [say_binary, "-o", str(output_path)]
            if voice and voice != "default":
                command.extend(["-v", voice])
            command.append(text)
            subprocess.run(command, check=True, capture_output=True)
            return str(output_path)

        wav_path = output_path.with_suffix(".wav")
        with wave.open(str(wav_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(22050)
            wav_file.writeframes(b"\x00\x00" * 22050 * max(8, min(360, len(text) // 6)))
        return str(wav_path)

    def _local_talking_avatar_preview(self, portrait_path: str, audio_path: str) -> str:
        from moviepy.editor import AudioFileClip, VideoClip
        from PIL import Image, ImageDraw, ImageFont
        import numpy as np

        audio = AudioFileClip(audio_path)
        duration = min(max(audio.duration, 6), 360)
        output_path = self._asset_path("digital-human", "talking-avatar-preview.mp4")
        portrait = Image.open(portrait_path).convert("RGB")
        frame_size = (1080, 1920)
        font = self._load_font(38)
        small_font = self._load_font(28)

        def make_frame(t: float):
            scale = max(frame_size[0] / portrait.width, frame_size[1] / portrait.height) * (1.0 + 0.025 * t / duration)
            resized = portrait.resize((int(portrait.width * scale), int(portrait.height * scale)), Image.Resampling.LANCZOS)
            x = (resized.width - frame_size[0]) // 2
            y = min((resized.height - frame_size[1]) // 2, 0)
            frame = resized.crop((x, y, x + frame_size[0], y + frame_size[1]))

            overlay = Image.new("RGBA", frame_size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            draw.rectangle((0, 1540, 1080, 1920), fill=(9, 17, 31, 152))
            draw.text((62, 1570), "李明亮｜重庆苏适酒店开发副总裁", fill=(255, 255, 255, 238), font=small_font)
            subtitle = self._subtitle_for_time(t, duration)
            self._draw_multiline_center(draw, subtitle, font, y=1642, max_width=930)
            frame = Image.alpha_composite(frame.convert("RGBA"), overlay)
            return np.array(frame.convert("RGB"))

        clip = VideoClip(make_frame, duration=duration).set_audio(audio.subclip(0, duration))
        clip.write_videofile(
            str(output_path),
            fps=24,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            bitrate="4500k",
            verbose=False,
            logger=None,
        )
        audio.close()
        clip.close()
        return str(output_path)

    def _subtitle_for_time(self, t: float, duration: float) -> str:
        lines = [
            "大家好，我是李明亮。",
            "重庆苏适酒店把江景旅居和智慧体验结合起来。",
            "自助入住、智能客控、机器人服务，让住客少等待、少打扰。",
            "对酒店来说，服务响应、能耗和运营都能被系统化管理。",
            "科技不该冰冷，而要更安静、更高效、更有温度。",
        ]
        index = min(len(lines) - 1, int((t / max(duration, 1)) * len(lines)))
        return lines[index]

    def _subtitle_events(self, text: str, duration: float) -> list[tuple[float, float, str]]:
        sentences: list[str] = []
        current = ""
        for char in text.replace("\n", " "):
            current += char
            if char in "。？！；.!?;":
                if current.strip():
                    sentences.append(current.strip())
                current = ""
        if current.strip():
            sentences.append(current.strip())
        if not sentences:
            return [(0, duration, "")]
        weights = [max(8, len(sentence)) for sentence in sentences]
        total_weight = sum(weights)
        events: list[tuple[float, float, str]] = []
        start = 0.0
        for sentence, weight in zip(sentences, weights):
            end = min(duration, start + duration * weight / total_weight)
            events.append((start, end, sentence))
            start = end
        events[-1] = (events[-1][0], duration, events[-1][2])
        return events

    def _template_title_lines(self, title: str) -> tuple[str, str]:
        cleaned = str(title or "").replace("\n", " ").strip()
        for delimiter in ("，", "？", "！", "：", " ", ",", "?", "!", ":"):
            if delimiter in cleaned and len(cleaned) > 14:
                parts = [part.strip() for part in cleaned.split(delimiter) if part.strip()]
                if len(parts) >= 2:
                    return parts[0][:18], "".join(parts[1:])[:18]
        midpoint = max(6, min(len(cleaned) - 1, len(cleaned) // 2))
        return cleaned[:midpoint][:18] or "公司方案讲解", cleaned[midpoint:][:18] or "数字人口播模板"

    def _template_card_segments(
        self,
        storyboard_plan: str | list[dict[str, object]] | None,
        duration: float,
    ) -> list[dict[str, object]]:
        structured = self._media_storyboard_plan(storyboard_plan, int(duration))
        cards = [
            item
            for item in structured
            if str(item.get("shot_type") or "").lower() not in {"talking_head", "person", "host"}
        ]
        if cards:
            return cards[:6]
        default_starts = [duration * 0.12, duration * 0.32, duration * 0.62]
        default_titles = ["核心流程", "关键数据", "落地价值"]
        default_visuals = [
            "用一张流程图讲清系统如何联动。",
            "用看板或表格展示运营变化。",
            "用三点总结让用户记住方案。",
        ]
        return [
            {
                "title": default_titles[index],
                "screen_text": default_titles[index],
                "visual": default_visuals[index],
                "start_second": int(start),
                "duration_seconds": max(4, min(8, int(duration * 0.11))),
            }
            for index, start in enumerate(default_starts)
        ]

    def _load_font(self, size: int):
        from PIL import ImageFont

        for path in (
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
        ):
            if Path(path).exists():
                return ImageFont.truetype(path, size=size)
        return ImageFont.load_default()

    def _draw_multiline_center(self, draw, text: str, font, y: int, max_width: int) -> None:
        words = list(text)
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = current + word
            if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        for line in lines[:3]:
            bbox = draw.textbbox((0, 0), line, font=font)
            x = (1080 - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, fill=(255, 255, 255, 245), font=font)
            y += 58

    def _asset_path(self, category: str, filename: str) -> Path:
        folder = self.storage_dir / category / uuid4().hex
        folder.mkdir(parents=True, exist_ok=True)
        return folder / filename

    def _clip_duration_for_duration(self, duration_seconds: int) -> int:
        return 10 if duration_seconds >= 60 else 5

    def _clip_count_for_duration(self, duration_seconds: int) -> int:
        clip_duration = self._clip_duration_for_duration(duration_seconds)
        return max(1, min(36, math.ceil(max(duration_seconds, clip_duration) / clip_duration)))

    def _segment_prompt(self, prompt: str, index: int, total: int) -> str:
        if total <= 1:
            return prompt
        return (
            f"{prompt.strip()}\n"
            f"Segment {index + 1} of {total}: create only this part of the video, "
            "keep visual continuity, avoid ending cards until the final segment."
        )

    def _seedance_prompt(self, prompt: str, duration_seconds: int = 5) -> str:
        safe_duration = max(5, min(10, duration_seconds))
        controls = f"--ratio 9:16 --resolution 480p --dur {safe_duration} --fps 24"
        if "--ratio" in prompt or "--resolution" in prompt or "--dur" in prompt:
            return prompt
        return f"{prompt.strip()} {controls}"

    def _seedance_video_url(self, task_data: dict[str, object]) -> Optional[str]:
        content = task_data.get("content")
        if isinstance(content, dict):
            for key in ("video_url", "url", "output_url"):
                value = content.get(key)
                if isinstance(value, str) and value:
                    return value
        return None

    def _mock_asset(self, category: str, filename: str) -> str:
        return f"mock://{category}/{filename}"

    def _extract_media_url(self, result: dict[str, object], fallback_key: str) -> str:
        for key in ("url", "video_url", "audio_url", "output_url", "path", "output_path"):
            value = result.get(key)
            if isinstance(value, str) and value:
                return value
        data = result.get("data")
        if isinstance(data, dict):
            return self._extract_media_url(data, fallback_key)
        return f"mock://{fallback_key}/{uuid4().hex}"

    def _extract_clip_list(self, result: dict[str, object]) -> list[str]:
        for key in ("clips", "videos", "outputs", "data"):
            value = result.get(key)
            if isinstance(value, list):
                clips = []
                for item in value:
                    if isinstance(item, str):
                        clips.append(item)
                    elif isinstance(item, dict):
                        clips.append(self._extract_media_url(item, "seedance"))
                if clips:
                    return clips
        return [self._extract_media_url(result, "seedance")]

    def _extract_voice_id(self, result: dict[str, object]) -> Optional[str]:
        for key in ("voice_id", "speaker_id", "voice", "id"):
            value = result.get(key)
            if isinstance(value, str) and value:
                return value
        data = result.get("data")
        if isinstance(data, dict):
            return self._extract_voice_id(data)
        return None

    def _is_local_path(self, value: str) -> bool:
        return bool(value) and not value.startswith("mock://") and not value.startswith("http")
