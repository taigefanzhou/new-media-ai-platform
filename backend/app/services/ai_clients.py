from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import mimetypes
import re
import subprocess
import asyncio
import wave
import math
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote, urlencode, urlparse
from uuid import uuid4
import httpx
from app.core.config import get_settings
from app.services.export_profiles import resolve_export_profile
from app.services.video_skills import script_generation_requirements, skill_prompt_payload


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

KEYLESS_VOICE_CLONE_PROVIDERS = {"cosyvoice-clone", "f5-tts", "openvoice"}
KEYLESS_DIGITAL_HUMAN_PROVIDERS = {"http-json", "sadtalker", "volcengine-jimeng-digital-human"}
DASHSCOPE_TTS_PROVIDERS = {"aliyun-cosyvoice", "aliyun-tts"}
DASHSCOPE_VOICE_CLONE_PROVIDERS = {"aliyun-cosyvoice-clone"}
DID_DIGITAL_HUMAN_PROVIDERS = {"d-id", "did"}
ALIYUN_DIGITAL_HUMAN_PROVIDERS = {"aliyun-wan-s2v", "aliyun-liveportrait", "aliyun-videoretalk"}


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
        variation_instruction: str = "",
    ) -> GeneratedScript:
        topic = self._clean_topic(topic)
        if self.model_config and self.model_config.api_base and self.model_config.api_key:
            return await self._openai_compatible(
                topic,
                brand_voice,
                duration_seconds,
                target_platform,
                output_language,
                variation_instruction,
            )
        if self.settings.llm_provider == "stub":
            return self._stub(topic, brand_voice, duration_seconds, target_platform, output_language)
        if self.settings.llm_provider == "openai-compatible":
            return await self._openai_compatible(
                topic,
                brand_voice,
                duration_seconds,
                target_platform,
                output_language,
                variation_instruction,
            )
        return self._stub(topic, brand_voice, duration_seconds, target_platform, output_language)

    async def _openai_compatible(
        self,
        topic: str,
        brand_voice: str,
        duration_seconds: int,
        target_platform: str,
        output_language: str = "zh-CN",
        variation_instruction: str = "",
    ) -> GeneratedScript:
        api_base = self.model_config.api_base if self.model_config else self.settings.llm_api_base
        api_key = self.model_config.api_key if self.model_config else self.settings.llm_api_key
        model_name = self.model_config.model_name if self.model_config else self.settings.llm_model
        if not api_base or not api_key:
            return self._stub(topic, brand_voice, duration_seconds, target_platform, output_language)

        profile = resolve_export_profile(platform=target_platform)
        prompt = {
            "topic": topic,
            "variation_instruction": variation_instruction,
            "brand_voice": brand_voice,
            "duration_seconds": duration_seconds,
            "target_platform": target_platform,
            "output_language": output_language,
            "export_profile": {
                "label": profile.label,
                "final_width": profile.width,
                "final_height": profile.height,
                "final_aspect_ratio": profile.aspect_ratio,
                "video_generation_ratio": profile.generation_ratio,
                "fit_mode": profile.fit_mode,
                "notes": profile.notes,
            },
            "built_in_realism_preset": SCRIPT_REALISM_PRESET,
            "built_in_video_production_skills": skill_prompt_payload(),
            "requirements": [
                *script_generation_requirements(),
                "如果 output_language 是 en-US，所有 hook、voiceover、title_options、hashtags、compliance_notes 必须使用英文；否则使用中文",
                "不要复刻或搬运任何参考视频原文",
                "适合公司新媒体账号和数字人口播",
                "默认套用 built_in_realism_preset，让脚本、分镜、口播动作、声音语气和画面提示词都更接近真实实拍",
                "口播稿要像真实负责人表达：先给结论，再讲场景，再讲方案，最后给行动建议",
                "不要使用“赋能、闭环、降本增效、领先、首选”等空泛词，除非能接具体场景或数据边界",
                "严格按 duration_seconds 控制口播长度：30秒约120字中文，60秒约220字中文，180秒约650字中文，360秒约1200字中文",
                "如果 duration_seconds 大于等于60秒，脚本必须是完整连贯结构，不能重复堆砌；按问题、误区、方案、案例、总结推进",
                "storyboard_plan 必须是数组，每段 10-20 秒，180秒至少9段，360秒至少18段",
                "storyboard_plan 每项必须包含：start_second,end_second,shot_type,visual,person_action,screen_text,asset_or_background,ai_prompt,needs_lip_sync,edit_intent,transition,audio_cue,color_note,caption_emphasis",
                "分镜要能真正执行：说明镜头如何动、画面元素如何变化、屏幕文字如何出现；不能只写“继续讲解”",
                "所有画面策划必须符合 export_profile；最终画幅按 final_width/final_height 输出，视频生成提示词按 video_generation_ratio 生成",
                "ai_prompt 始终使用英文，适合 Seedance 或其他视频模型；必须包含目标画幅、自然皮肤、真实灯光、非塑料感、非机械感、clean plate、no on-screen text、no watermark、consistent background 等真实口播要求",
                "seedance_prompt 始终使用英文，必须包含 realistic live-action talking-head style、natural skin texture、natural speech rhythm、clean plate、no on-screen text、no watermark 和 video_generation_ratio",
                "必须输出严格 JSON",
                "variation_instruction 只是给模型看的内部差异化要求，绝不能逐字出现在 hook、voiceover、storyboard、storyboard_plan、seedance_prompt、title_options 或字幕文字里",
                "hook 和 voiceover 只能包含最终用户能听到的自然口播内容，不得包含“批量生成第几条”“请换一个标题角度”“避免与其他脚本重复”等内部工作流文字",
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
                        "edit_intent": "该镜头在叙事中的作用",
                        "transition": "hard_cut / J_cut / L_cut / dissolve",
                        "audio_cue": "旁白、环境声、BGM或音效节点",
                        "color_note": "曝光、白平衡、肤色和镜头匹配要求",
                        "caption_emphasis": ["关键词"],
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

        async with httpx.AsyncClient(timeout=180, trust_env=False) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        usage = data.get("usage") or {}
        storyboard_plan = self._normalize_storyboard_plan(parsed.get("storyboard_plan"), parsed.get("storyboard", ""), duration_seconds)
        return GeneratedScript(
            hook=self._strip_internal_instructions(parsed.get("hook", "")),
            voiceover=self._strip_internal_instructions(parsed.get("voiceover", "")),
            storyboard=self._strip_internal_instructions(parsed.get("storyboard", "")),
            storyboard_plan=self._clean_storyboard_plan(storyboard_plan),
            seedance_prompt=self._strip_internal_instructions(parsed.get("seedance_prompt", "")),
            title_options=self._strip_internal_instructions(parsed.get("title_options", "")),
            hashtags=self._strip_internal_instructions(parsed.get("hashtags", "")),
            compliance_notes=self._strip_internal_instructions(parsed.get("compliance_notes", "")),
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
        topic = self._clean_topic(topic)
        profile = resolve_export_profile(platform=target_platform)
        profile_prompt = (
            f"target generation ratio {profile.generation_ratio}, final export {profile.width}x{profile.height} "
            f"{profile.aspect_ratio}, {profile.label}"
        )
        if output_language == "en-US":
            voiceover = self._stub_voiceover_en(topic, duration_seconds)
            storyboard = self._stub_storyboard_en(topic, duration_seconds)
            storyboard_plan = self._stub_storyboard_plan(topic, duration_seconds, "en-US", target_platform)
            return GeneratedScript(
                hook=f"The real value of {topic} is not convenience alone, but smarter hotel operations.",
                voiceover=voiceover,
                storyboard=storyboard,
                storyboard_plan=storyboard_plan,
                seedance_prompt=(
                    f"{profile_prompt}, long-form business explainer video, consistent modern hotel lobby and guest room, "
                    "smart operations dashboard, realistic live-action talking-head style, natural skin texture, "
                    "relaxed facial expression, natural speech rhythm, smooth transitions, professional lighting, "
                    "continuity across segments, clean plate, no on-screen text, no plastic skin, no robotic pose, "
                    "no watermark, no third-party logos."
                ),
                title_options=(
                    "1. Smarter Hotel Energy Control\n"
                    "2. No-Card Power Solution for Modern Hotels\n"
                    "3. Better Guest Experience, Lower Energy Waste"
                ),
                hashtags="#HotelTech #SmartHotel #EnergySaving #Hospitality",
                compliance_notes=(
                    "Built-in video production skills enabled: learn structure only from references, keep clean plates, "
                    "verify face stability, subtitles, watermark, script alignment, and asset rights before publishing."
                ),
            )
        voiceover = self._stub_voiceover_zh(topic, duration_seconds)
        storyboard = self._stub_storyboard_zh(topic, duration_seconds)
        storyboard_plan = self._stub_storyboard_plan(topic, duration_seconds, "zh-CN", target_platform)
        return GeneratedScript(
            hook=f"你有没有发现，{topic}真正影响结果的不是选择多，而是判断标准。",
            voiceover=voiceover,
            storyboard=storyboard,
            storyboard_plan=storyboard_plan,
            seedance_prompt=(
                f"{profile_prompt}, long-form corporate explainer video, consistent presenter and modern business hotel scenes, "
                "clear chapter-like progression, smart operations interface, realistic live-action talking-head style, "
                "natural skin texture, relaxed facial expression, medium speech pace, smooth transitions, professional lighting, "
                "clean plate, no on-screen text, no plastic skin, no robotic pose, no third-party logos, no watermark."
            ),
            title_options=(
                f"1. {topic}怎么选？看这3点\n"
                f"2. 别再盲选{topic}了\n"
                f"3. {topic}的关键判断标准"
            ),
            hashtags=f"#{target_platform} #企业服务 #数字人 #短视频运营",
            compliance_notes="已启用视频生产 Skill：参考视频只学结构不搬运；底片不生成内嵌文字；成片需检查脸部稳定、字幕、水印、脚本一致性和素材版权。",
        )

    def _stub_voiceover_zh(self, topic: str, duration_seconds: int) -> str:
        topic = self._clean_topic(topic)
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
        topic = self._clean_topic(topic)
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

    def _stub_storyboard_plan(
        self,
        topic: str,
        duration_seconds: int,
        output_language: str,
        target_platform: str | None = None,
    ) -> list[dict[str, object]]:
        topic = self._clean_topic(topic)
        profile = resolve_export_profile(platform=target_platform)
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
                        f"{profile.label}, generation ratio {profile.generation_ratio}, realistic business hotel video, {shot_type}, {visual}, "
                        f"topic: {topic}, natural skin texture, relaxed facial expression, medium speech pace, "
                        "smooth motion, clean plate, no on-screen text, professional lighting, no plastic skin, no robotic pose, no watermark"
                    ),
                    "needs_lip_sync": shot_type == "talking_head",
                    "edit_intent": "开场建立主题" if index == 0 else "收束行动建议" if index == segment_count - 1 else "推进当前信息并提供视觉证据",
                    "transition": "hard_cut",
                    "audio_cue": "narration_priority",
                    "color_note": "match exposure and white balance; preserve natural skin tone",
                    "caption_emphasis": [],
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
                    "edit_intent": str(item.get("edit_intent") or "推进当前信息并保持叙事连续"),
                    "transition": str(item.get("transition") or "hard_cut"),
                    "audio_cue": str(item.get("audio_cue") or "narration_priority"),
                    "color_note": str(item.get("color_note") or "match exposure and white balance; preserve natural skin tone"),
                    "caption_emphasis": item.get("caption_emphasis") if isinstance(item.get("caption_emphasis"), list) else [],
                }
            )
        return normalized or self._plan_from_storyboard_lines(storyboard, duration_seconds)

    @staticmethod
    def _clean_topic(topic: str) -> str:
        lines = []
        for line in str(topic or "").splitlines():
            cleaned = line.strip()
            if not cleaned:
                continue
            if re.match(r"^批量生成第\s*\d+\s*条[:：]", cleaned):
                continue
            lines.append(cleaned)
        return "\n".join(lines).strip() or str(topic or "").strip()

    @staticmethod
    def _strip_internal_instructions(value: object) -> str:
        text = str(value or "")
        patterns = [
            r"\s*批量生成第\s*\d+\s*条[:：][^。\n]*[。.]?",
            r"\s*请换一个标题角度、开头钩子和分镜结构，?避免与其他脚本重复[。.]?",
            r"\s*避免与其他脚本重复[。.]?",
        ]
        for pattern in patterns:
            text = re.sub(pattern, "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"。。+", "。", text)
        text = re.sub(r"：\s*。", "：", text)
        return text.strip()

    def _clean_storyboard_plan(self, plan: list[dict[str, object]]) -> list[dict[str, object]]:
        cleaned = []
        for item in plan:
            next_item = {}
            for key, value in item.items():
                next_item[key] = self._strip_internal_instructions(value) if isinstance(value, str) else value
            cleaned.append(next_item)
        return cleaned

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
                    "ai_prompt": f"Vertical 9:16 realistic business hotel video, {line}, smooth camera motion, clean plate, no on-screen text, no watermark",
                    "needs_lip_sync": index in (0, len(lines) - 1),
                    "edit_intent": "开场建立主题" if index == 0 else "收束行动建议" if index == len(lines) - 1 else "推进解释并提供视觉变化",
                    "transition": "hard_cut",
                    "audio_cue": "narration_priority",
                    "color_note": "match exposure and white balance; preserve natural skin tone",
                    "caption_emphasis": [],
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
        digital_human_platform_credential=None,
        storage_dir: str | Path | None = None,
    ) -> None:
        self.settings = get_settings()
        self.video_model_config = video_model_config
        self.tts_model_config = tts_model_config
        self.digital_human_model_config = digital_human_model_config
        self.digital_human_platform_credential = digital_human_platform_credential
        self.storage_dir = Path(storage_dir or self.settings.storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    async def synthesize_voice(self, text: str, voice: Optional[str] = None) -> str:
        api_base = self.tts_model_config.api_base if self.tts_model_config and self.tts_model_config.api_base else self.settings.tts_api_base
        api_key = self.tts_model_config.api_key if self.tts_model_config and self.tts_model_config.api_key else self.settings.tts_api_key
        provider = self.tts_model_config.provider if self.tts_model_config else self.settings.tts_provider
        model_name = self.tts_model_config.model_name if self.tts_model_config else self.settings.tts_voice
        default_voice = (
            self._config_note_value(self.tts_model_config, "voice")
            or self._config_note_value(self.tts_model_config, "default_voice")
            or self.settings.tts_voice
        )
        if default_voice == "default":
            default_voice = "longanyang"
        if self._is_dashscope_tts(provider, api_base):
            if not api_base:
                raise RuntimeError("百炼 CosyVoice 接口地址未配置，请使用 https://dashscope.aliyuncs.com/api/v1")
            if not api_key:
                raise RuntimeError("百炼 CosyVoice API Key 未配置")
            return await self._synthesize_dashscope_cosyvoice(
                text,
                voice or default_voice or "longanyang",
                api_base,
                api_key,
                model_name or "cosyvoice-v3-flash",
            )
        if provider == "mock" or not api_base:
            return self._local_voiceover(text, voice)

        payload = {
            "text": text,
            "voice": voice or default_voice or model_name,
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
        source_url: Optional[str] = None,
    ) -> str:
        api_base = model_config.api_base if model_config and model_config.api_base else self.settings.voice_clone_api_base
        api_key = model_config.api_key if model_config and model_config.api_key else self.settings.voice_clone_api_key
        provider = model_config.provider if model_config else self.settings.voice_clone_provider
        if not api_base:
            raise RuntimeError("Voice clone service is not configured")
        if self._is_dashscope_voice_clone(provider, api_base):
            if not api_key:
                raise RuntimeError("百炼 CosyVoice 声音复刻 API Key 未配置")
            return await self._clone_dashscope_cosyvoice(
                source_video_path,
                source_url,
                speaker_name,
                api_base,
                api_key,
                model_config,
            )
        if not api_key and provider not in KEYLESS_VOICE_CLONE_PROVIDERS:
            raise RuntimeError("Voice clone API key is not configured")

        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        data = {
            "provider": provider,
            "speaker_name": speaker_name,
        }
        with open(source_video_path, "rb") as source_file:
            files = {
                "source_video": (Path(source_video_path).name, source_file, "video/mp4"),
            }
            async with httpx.AsyncClient(timeout=900, trust_env=False) as client:
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
        portrait_url: Optional[str] = None,
        source_video_url: Optional[str] = None,
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
        if not api_key and provider not in KEYLESS_DIGITAL_HUMAN_PROVIDERS:
            raise RuntimeError("Digital human API key is not configured")
        if self._is_aliyun_digital_human_provider(provider):
            return await self._generate_aliyun_digital_human(
                portrait_path,
                audio_path,
                source_video_path,
                api_base,
                api_key,
                provider,
                self.digital_human_model_config.model_name if self.digital_human_model_config else provider,
                portrait_url,
                source_video_url,
            )
        if self._is_did_provider(provider):
            return await self._generate_did_talk(portrait_path, audio_path, api_base, api_key, style_prompt)
        if self._is_volcengine_jimeng_provider(provider):
            return await self._generate_volcengine_jimeng_video(
                portrait_path,
                source_video_path,
                api_base,
                style_prompt,
                portrait_url,
                source_video_url,
            )

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
        api_key = (
            self.digital_human_model_config.api_key
            if self.digital_human_model_config and self.digital_human_model_config.api_key
            else self.settings.digital_human_api_key
        )
        if not api_base or provider == "mock":
            return False
        return bool(api_key) or provider in KEYLESS_DIGITAL_HUMAN_PROVIDERS

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
        export_profile: str | None = None,
        reference_media: list[dict[str, object]] | None = None,
    ) -> str:
        provider = self.video_model_config.provider if self.video_model_config else self.settings.video_generation_provider
        api_base = self.video_model_config.api_base if self.video_model_config and self.video_model_config.api_base else ""
        api_key = self.video_model_config.api_key if self.video_model_config and self.video_model_config.api_key else self.settings.seedance_api_key
        if "seedance" in provider:
            if not api_key:
                raise RuntimeError("Seedance API Key 未配置，无法生成真实视频。")
            return await self._generate_seedance_clip_via_ark(
                self._segment_prompt(prompt, index, total),
                duration_seconds,
                export_profile,
                reference_media=reference_media,
            )

        if "seedance" in provider and self.settings.seedance_api_base:
            if not self.settings.seedance_api_key:
                raise RuntimeError("Seedance API Key 未配置，无法生成真实视频。")
            return await self._generate_seedance_clip_via_ark(
                self._segment_prompt(prompt, index, total),
                duration_seconds,
                export_profile,
                reference_media=reference_media,
            )

        comfyui_base = api_base if provider == "comfyui" else self.settings.comfyui_api_base
        if provider == "comfyui" and comfyui_base:
            payload = {
                "prompt": prompt,
                "duration_seconds": duration_seconds,
                "segment_index": index + 1,
                "segment_count": total,
                "workflow": "default-video-generation",
            }
            result = await self._post_media(comfyui_base, "/prompt", payload)
            return self._extract_media_url(result, "comfyui_job")

        raise RuntimeError("没有可用的真实视频生成模型，请启用 Seedance 或 ComfyUI 视频模型。")

    def segment_plan(
        self,
        prompt: str,
        storyboard: str,
        duration_seconds: int = 30,
        storyboard_plan: str | list[dict[str, object]] | None = None,
    ) -> list[dict[str, object]]:
        structured_plan = self._media_storyboard_plan(storyboard_plan, duration_seconds)
        timed_plan = self._timed_action_plan(storyboard, duration_seconds, structured_plan)
        if timed_plan:
            return timed_plan
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

    def _timed_action_plan(
        self,
        storyboard: str,
        duration_seconds: int,
        structured_plan: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        if len(structured_plan) != 1 or not 8 <= duration_seconds <= 15:
            return []
        range_token = r"\d+\s*[-—–~至到]\s*\d+\s*秒\s*[：:]"
        matches = re.findall(
            rf"(\d+)\s*[-—–~至到]\s*(\d+)\s*秒\s*[：:]\s*(.*?)(?={range_token}|$)",
            storyboard or "",
            flags=re.DOTALL,
        )
        beats = [
            (int(start), int(end), description.strip(" \n。；;"))
            for start, end, description in matches
            if int(start) < int(end) and description.strip()
        ]
        if not 2 <= len(beats) <= 3 or beats[0][0] != 0 or beats[-1][1] != duration_seconds:
            return []
        if any(end - start < 4 or end - start > 8 for start, end, _ in beats):
            return []

        source = structured_plan[0]
        scene = str(source.get("asset_or_background") or "同一场景、光线和道具布局")
        camera = str(source.get("shot_type") or "稳定中近景")
        source_prompt = str(source.get("prompt") or "").strip()
        plan: list[dict[str, object]] = []
        for index, (start, end, action) in enumerate(beats, start=1):
            item = dict(source)
            item.update(
                {
                    "title": f"第 {index} 镜 · {action[:16]}",
                    "start_second": start,
                    "duration_seconds": end - start,
                    "prompt": (
                        "Vertical realistic live-action shot. "
                        f"Global visual specification (keep identity, colors, props and scene details; ignore its timing sequence): {source_prompt}. "
                        f"Scene continuity lock: {scene}. Camera: {camera}. "
                        f"This segment only: {action}. "
                        "Keep the same presenter, outfit, lighting, architecture and exact prop design as adjacent segments. "
                        "One simple action only, natural motion, no extra people, no embedded text, no logo, no watermark."
                    ),
                    "person_action": action,
                }
            )
            plan.append(item)
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
                    "reference_material_id": item.get("reference_material_id"),
                    "edit_intent": str(item.get("edit_intent") or ""),
                    "transition": str(item.get("transition") or "hard_cut"),
                    "audio_cue": str(item.get("audio_cue") or ""),
                    "color_note": str(item.get("color_note") or ""),
                    "caption_emphasis": item.get("caption_emphasis") if isinstance(item.get("caption_emphasis"), list) else [],
                }
            )
        return plan

    async def compose_final_video(
        self,
        clips: list[str],
        avatar_clip: str,
        export_profile: str | None = None,
    ) -> str:
        if self.settings.composition_provider != "ffmpeg":
            if self._is_local_path(avatar_clip):
                return self._export_to_profile(avatar_clip, export_profile)
            local_clip = next((item for item in clips if self._is_local_path(item)), None)
            if local_clip:
                return self._export_to_profile(local_clip, export_profile)
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
        export_profile: str | None = None,
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
        return self._export_to_profile(str(output_path), export_profile)

    async def material_to_scene_clip(
        self,
        material_path: str,
        duration_seconds: int = 5,
        export_profile: str | None = None,
    ) -> str:
        path = Path(material_path)
        if not path.exists() or not path.is_file():
            raise RuntimeError("素材文件不存在，无法生成分镜片段。")
        mime_type = mimetypes.guess_type(str(path))[0] or ""
        if mime_type.startswith("video/"):
            return str(path)

        from moviepy.editor import ImageClip

        profile = resolve_export_profile(export_profile)
        output_path = self._asset_path("composition", "material-image-clip.mp4")
        clip = ImageClip(str(path)).set_duration(max(3, min(12, int(duration_seconds or 5))))
        scale = max(profile.width / clip.w, profile.height / clip.h)
        clip = clip.resize(scale)
        clip = clip.crop(
            x_center=clip.w / 2,
            y_center=clip.h / 2,
            width=profile.width,
            height=profile.height,
        )
        clip.write_videofile(
            str(output_path),
            fps=24,
            codec="libx264",
            audio=False,
            preset="medium",
            bitrate="2200k",
            threads=2,
            logger=None,
        )
        clip.close()
        return str(output_path)

    async def compose_talking_avatar_sequence(self, avatar_clips: list[str]) -> str:
        from moviepy.editor import VideoFileClip, concatenate_videoclips

        local_inputs = [item for item in avatar_clips if self._is_local_path(item) and Path(item).exists()]
        if not local_inputs:
            return self._mock_asset("digital-human", "talking-avatar-sequence.mp4")

        output_path = self._asset_path("digital-human", "talking-avatar-sequence.mp4")
        clips = []
        final_clip = None
        try:
            for path in local_inputs:
                clips.append(VideoFileClip(path))
            final_clip = concatenate_videoclips(clips, method="compose")
            final_clip.write_videofile(
                str(output_path),
                fps=24,
                codec="libx264",
                audio_codec="aac",
                preset="medium",
                bitrate="3600k",
                threads=4,
                verbose=False,
                logger=None,
            )
        finally:
            if final_clip is not None:
                final_clip.close()
            for clip in clips:
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
        export_profile: str | None = None,
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
            main = video_image(t, (720, main_h))
            canvas.paste(main, (0, top_h))
            overlay = Image.new("RGBA", frame_size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            overlay_draw.rectangle((0, top_h, 720, top_h + main_h), fill=(0, 0, 0, 12))
            overlay_draw.rounded_rectangle(
                (46, bottom_y - 74, 674, bottom_y - 20),
                radius=18,
                fill=(2, 6, 23, 118),
                outline=(255, 255, 255, 60),
                width=2,
            )
            canvas.alpha_composite(overlay)
            screen_text = str(card.get("title") or card.get("screen_text") or "方案要点")
            visual = str(card.get("visual") or card.get("prompt") or "")
            draw = ImageDraw.Draw(canvas)
            draw.text((72, bottom_y - 60), f"{screen_text[:10]} · {visual[:22]}", font=meta_font, fill=(255, 255, 255, 235))
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
        return self._export_to_profile(str(output_path), export_profile)

    async def compose_dynamic_explainer(
        self,
        voiceover: str,
        storyboard_plan: str | list[dict[str, object]] | None,
        audio_path: str,
        portrait_path: Optional[str] = None,
        duration_seconds: int = 30,
        export_profile: str | None = None,
    ) -> str:
        from moviepy.editor import AudioClip, AudioFileClip, CompositeAudioClip, VideoClip
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
        return self._export_to_profile(str(output_path), export_profile)

    async def compose_wechat_reference_template(
        self,
        voiceover: str,
        storyboard_plan: str | list[dict[str, object]] | None,
        audio_path: str,
        title: str,
        duration_seconds: int = 60,
        export_profile: str | None = None,
    ) -> str:
        from moviepy.editor import AudioClip, AudioFileClip, CompositeAudioClip, VideoClip
        from PIL import Image, ImageDraw, ImageFilter, ImageFont
        import numpy as np

        audio = AudioFileClip(audio_path)
        duration = min(max(audio.duration, 6), max(duration_seconds, 6))
        output_path = self._asset_path("final", "wechat-reference-template.mp4")
        frame_size = (1280, 720)
        serif_path = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"
        serif = lambda size: ImageFont.truetype(serif_path, size=size) if Path(serif_path).exists() else self._load_font(size)
        title_font = serif(40)
        subtitle_font = serif(44)
        label_font = serif(42)
        brand_font = serif(28)
        red = (220, 38, 38)
        white = (248, 248, 244)
        subtitle_phrases: list[str] = []
        for _, _, sentence in self._subtitle_events(voiceover, duration):
            clean = sentence.strip("。！？；，,.!?; ")
            chunks = [
                clean[index:index + 14].strip("。！？；，,.!?; ")
                for index in range(0, len(clean), 14)
                if clean[index:index + 14].strip("。！？；，,.!?; ")
            ]
            if len(chunks) > 1 and len(chunks[-1]) < 6:
                tail = chunks.pop()
                chunks[-1] += tail
            subtitle_phrases.extend(chunks)
        subtitle_phrases = subtitle_phrases or [title]
        display_title = re.sub(r"^\s*\d+[.、]\s*", "", title).strip() or title

        def wrap_text(text: str, limit: int, max_lines: int) -> list[str]:
            lines: list[str] = []
            current = ""
            for char in str(text or "").replace("\n", " "):
                current += char
                if len(current) >= limit:
                    lines.append(current)
                    current = ""
            if current:
                lines.append(current)
            return lines[:max_lines]

        def dialog_for_time(t: float) -> tuple[str, str]:
            index = min(len(subtitle_phrases) - 1, int(t / 4.0))
            phrase = subtitle_phrases[index]
            return (phrase, "") if index % 2 == 0 else ("", phrase)

        def text_width(draw, text: str, font, stroke: int = 0) -> int:
            bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
            return bbox[2] - bbox[0]

        def draw_center(draw, text: str, y: int, font, fill=white, stroke: int = 0):
            width = text_width(draw, text, font, stroke)
            draw.text(
                ((frame_size[0] - width) // 2, y),
                text,
                font=font,
                fill=fill,
                stroke_width=stroke,
                stroke_fill=(0, 0, 0),
            )

        def draw_center_fit(draw, text: str, y: int, font, fill=white, max_width: int = 610, stroke: int = 0):
            value = str(text or "")
            while value and text_width(draw, value, font, stroke) > max_width:
                value = value[:-1]
            draw_center(draw, value, y, font, fill, stroke)

        def draw_text_fit(draw, xy: tuple[int, int], text: str, font, fill=white, max_width: int = 560, stroke: int = 0):
            value = str(text or "")
            while value and text_width(draw, value, font, stroke) > max_width:
                value = value[:-1]
            draw.text(
                xy,
                value,
                font=font,
                fill=fill,
                stroke_width=stroke,
                stroke_fill=(0, 0, 0),
            )

        def draw_wave(draw, t: float):
            mid_y = 330
            draw.line((150, mid_y, 1130, mid_y), fill=(255, 255, 255), width=1)
            for index in range(76):
                x = 380 + index * 7
                height = 8 + int(118 * abs(math.sin(t * 3.2 + index * 0.43)) * (1 - index / 105))
                draw.rounded_rectangle((x, mid_y - height, x + 4, mid_y), radius=2, fill=white)

        def draw_hotel_scene(canvas, t: float):
            scene = Image.new("RGB", (1280, 522), (82, 64, 45))
            draw = ImageDraw.Draw(scene)
            for y in range(522):
                shade = int(54 + y * 0.045)
                draw.line((0, y, 1280, y), fill=(shade + 22, shade + 10, shade))
            draw.polygon([(0, 80), (500, 210), (0, 522)], fill=(48, 42, 37))
            draw.rectangle((720, 74, 1280, 522), fill=(70, 58, 46))
            draw.rectangle((110, 258, 850, 454), fill=(180, 164, 138))
            draw.rectangle((150, 296, 810, 432), fill=(222, 212, 190))
            draw.rectangle((840, 160, 1130, 350), fill=(28, 43, 48))
            draw.rectangle((870, 188, 1100, 308), fill=(58, 120, 116))
            draw.rectangle((840, 368, 1220, 522), fill=(105, 86, 63))
            scene = Image.blend(scene.filter(ImageFilter.GaussianBlur(radius=2)), Image.new("RGB", scene.size), 0.34)
            canvas.paste(scene, (0, 88))

        def draw_dialog(draw, t: float):
            first, second = dialog_for_time(t)
            draw_text_fit(draw, (96, 380), f"A: {first}", subtitle_font, white, 1050, 3)
            draw.text((510, 480), f"B: {second}", font=label_font, fill=red, stroke_width=2, stroke_fill=(0, 0, 0))

        def make_frame(t: float):
            canvas = Image.new("RGB", frame_size, (0, 0, 0))
            draw = ImageDraw.Draw(canvas)
            draw_hotel_scene(canvas, t)
            draw_wave(draw, t)
            draw_dialog(draw, t)
            draw_center_fit(draw, f"「{display_title}」", 18, title_font, white, 1080, 2)
            brand = "酒店智能客控方案"
            left = (1280 - text_width(draw, brand, brand_font)) // 2
            draw.rectangle((0, 610, 1280, 720), fill=(0, 0, 0))
            draw.text((left - 24, 654), "—", font=brand_font, fill=white)
            draw.text((left, 654), brand[:4], font=brand_font, fill=white)
            draw.text((left + text_width(draw, brand[:4], brand_font), 654), brand[4:], font=brand_font, fill=red)
            draw.text((left + text_width(draw, brand, brand_font) + 2, 654), "—", font=brand_font, fill=white)
            return np.array(canvas)

        def bgm_frame(t):
            values = np.asarray(t)
            fade = np.minimum(1, np.minimum(values / 2.5, (duration - values) / 2.5))
            fade = np.maximum(0, fade)
            pad = (
                0.018 * np.sin(2 * np.pi * 146.83 * values)
                + 0.012 * np.sin(2 * np.pi * 220.00 * values)
                + 0.007 * np.sin(2 * np.pi * 329.63 * values)
            ) * fade
            if np.isscalar(t):
                return [float(pad), float(pad)]
            return np.column_stack([pad, pad])

        voice_track = audio.subclip(0, duration).volumex(1.0)
        music_track = AudioClip(bgm_frame, duration=duration, fps=44100)
        mixed_audio = CompositeAudioClip([music_track, voice_track])
        clip = VideoClip(make_frame, duration=duration).set_audio(mixed_audio)
        clip.write_videofile(
            str(output_path),
            fps=20,
            codec="libx264",
            audio_codec="aac",
            preset="ultrafast",
            bitrate="2400k",
            threads=2,
            verbose=False,
            logger=None,
        )
        mixed_audio.close()
        music_track.close()
        audio.close()
        clip.close()
        return str(output_path)

    async def _synthesize_dashscope_cosyvoice(
        self,
        text: str,
        voice: str,
        api_base: str,
        api_key: str,
        model_name: str,
    ) -> str:
        endpoint = self._dashscope_tts_endpoint(api_base)
        input_payload = self._dashscope_tts_input(text, voice, model_name)
        payload = {
            "model": model_name or "cosyvoice-v3-flash",
            "input": input_payload,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=240, trust_env=False) as client:
            response = await self._request_with_retries(client, "POST", endpoint, "百炼 CosyVoice 语音合成", headers=headers, json=payload)
            data = response.json()

        audio_url = self._nested_value(data, ("output", "audio", "url"))
        if isinstance(audio_url, str) and audio_url:
            try:
                audio_path = await self._download_media(audio_url, "voice", "voiceover.wav")
            except Exception:
                audio_path = await self._synthesize_dashscope_cosyvoice_stream(text, voice or "longanyang", api_base, api_key, model_name)
            Path(f"{audio_path}.source_url").write_text(audio_url, encoding="utf-8")
            return audio_path

        audio_data = self._nested_value(data, ("output", "audio", "data"))
        if isinstance(audio_data, str) and audio_data:
            if "," in audio_data:
                audio_data = audio_data.split(",", 1)[1]
            output_path = self._asset_path("voice", "voiceover.wav")
            output_path.write_bytes(base64.b64decode(audio_data))
            return str(output_path)
        raise RuntimeError("百炼 CosyVoice 未返回音频 URL 或音频数据")

    async def _synthesize_dashscope_cosyvoice_stream(
        self,
        text: str,
        voice: str,
        api_base: str,
        api_key: str,
        model_name: str,
    ) -> str:
        endpoint = self._dashscope_tts_endpoint(api_base)
        input_payload = self._dashscope_tts_input(text, voice, model_name)
        payload = {
            "model": model_name or "cosyvoice-v3-flash",
            "input": input_payload,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-DashScope-SSE": "enable",
        }
        chunks: list[bytes] = []
        async with httpx.AsyncClient(timeout=240, trust_env=False) as client:
            async with client.stream("POST", endpoint, headers=headers, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    event = json.loads(line.removeprefix("data:").strip())
                    audio_data = self._nested_value(event, ("output", "audio", "data"))
                    if isinstance(audio_data, str) and audio_data:
                        chunks.append(base64.b64decode(audio_data))
        if not chunks:
            raise RuntimeError("百炼 CosyVoice 流式合成未返回音频数据")
        output_path = self._asset_path("voice", "voiceover.wav")
        output_path.write_bytes(b"".join(chunks))
        return str(output_path)

    def _dashscope_tts_input(self, text: str, voice: str, model_name: str) -> dict[str, object]:
        enable_ssml = self._config_note_bool(self.tts_model_config, "enable_ssml")
        input_payload: dict[str, object] = {
            "text": self._text_to_ssml(text) if enable_ssml else text,
            "voice": voice or "longanyang",
            "format": self._config_note_value(self.tts_model_config, "format") or "wav",
            "sample_rate": self._config_note_int(self.tts_model_config, "sample_rate") or 24000,
        }
        instruction = self._config_note_value(self.tts_model_config, "instruction")
        if instruction:
            input_payload["instruction"] = instruction
        if enable_ssml:
            input_payload["enable_ssml"] = True
        for key in ("rate", "pitch", "volume"):
            value = self._config_note_float(self.tts_model_config, key)
            if value is not None:
                input_payload[key] = value
        return input_payload

    def _text_to_ssml(self, text: str) -> str:
        escaped = (
            str(text or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        escaped = re.sub(r"([。！？!?])", r"\\1<break time=\"450ms\"/>", escaped)
        escaped = re.sub(r"([；;])", r"\\1<break time=\"320ms\"/>", escaped)
        escaped = re.sub(r"([，,])", r"\\1<break time=\"180ms\"/>", escaped)
        return f"<speak>{escaped}</speak>"

    async def _clone_dashscope_cosyvoice(
        self,
        source_video_path: str,
        source_url: Optional[str],
        speaker_name: str,
        api_base: str,
        api_key: str,
        model_config=None,
    ) -> str:
        media_url = self._public_media_url(source_url or source_video_path)
        if not media_url:
            raise RuntimeError("百炼 CosyVoice 声音复刻需要公网可访问的音频/视频 URL，请先在素材里填写 source_url 或上传到 OSS。")
        target_model = (
            self._config_note_value(model_config, "target_model")
            or self._config_note_value(model_config, "tts_model")
            or (model_config.model_name if model_config else "")
            or "cosyvoice-v3-flash"
        )
        prefix = self._voice_prefix(speaker_name)
        payload = {
            "model": "voice-enrollment",
            "input": {
                "action": "create_voice",
                "target_model": target_model,
                "prefix": prefix,
                "url": media_url,
            },
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=300, trust_env=False) as client:
            response = await client.post(self._dashscope_customization_endpoint(api_base), headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        voice_id = self._extract_voice_id(data)
        if not voice_id:
            raise RuntimeError("百炼 CosyVoice 声音复刻未返回 voice_id")
        return voice_id

    async def _generate_aliyun_digital_human(
        self,
        portrait_path: Optional[str],
        audio_path: str,
        source_video_path: Optional[str],
        api_base: str,
        api_key: Optional[str],
        provider: str,
        model_name: str,
        portrait_url: Optional[str] = None,
        source_video_url: Optional[str] = None,
    ) -> str:
        if not api_key:
            raise RuntimeError("阿里云百炼数字人 API Key 未配置")
        audio_url = self._audio_source_url(audio_path) or self._public_media_url(audio_path)
        image_url = self._public_media_url(portrait_url) or self._public_media_url(portrait_path)
        video_url = self._public_media_url(source_video_url) or self._public_media_url(source_video_path)
        model = model_name or "wan2.2-s2v"

        if self._is_aliyun_videoretalk(provider, model):
            if not video_url:
                raise RuntimeError("阿里云 VideoRetalk 需要公网可访问的口播源视频 URL，请先把源视频素材补传服务器。")
            if not audio_url:
                raise RuntimeError("阿里云 VideoRetalk 需要公网可访问的音频 URL，请确认语音合成返回了公网音频地址。")
            input_payload: dict[str, object] = {"video_url": video_url, "audio_url": audio_url}
            if image_url and self._config_note_bool(self.digital_human_model_config, "use_ref_image"):
                input_payload["ref_image_url"] = image_url
            model = "videoretalk"
            parameters: dict[str, object] = {}
        else:
            if not image_url:
                raise RuntimeError("阿里云数字人需要公网可访问的头像图片 URL，请先在素材库把头像补传服务器。")
            if not audio_url:
                raise RuntimeError("阿里云数字人需要公网可访问的音频 URL，请确认语音合成返回了公网音频地址。")
            input_payload = {"image_url": image_url, "audio_url": audio_url}
            if self._is_aliyun_liveportrait(provider, model):
                model = "liveportrait"
                parameters = {
                    "template_id": self._config_note_value(self.digital_human_model_config, "template_id") or "normal",
                    "video_fps": 24,
                    "mouth_move_strength": 1,
                    "paste_back": True,
                }
            else:
                audio_duration = self._media_duration_seconds(audio_path)
                if audio_duration and audio_duration >= 20:
                    raise RuntimeError("阿里云 wan2.2-s2v 单次音频需小于 20 秒，长口播需要先切成 20 秒以内的分段。")
                model = "wan2.2-s2v"
                parameters = {"resolution": self._config_note_value(self.digital_human_model_config, "resolution") or "480P"}

        task_id = await self._submit_aliyun_video_synthesis_task(api_base, api_key, model, input_payload, parameters)
        result_url = await self._poll_aliyun_video_synthesis_task(api_base, api_key, task_id)
        return await self._download_media(result_url, "digital-human", f"{task_id}.mp4")

    async def _generate_volcengine_jimeng_video(
        self,
        portrait_path: Optional[str],
        source_video_path: Optional[str],
        api_base: str,
        style_prompt: str = "",
        portrait_url: Optional[str] = None,
        source_video_url: Optional[str] = None,
    ) -> str:
        credential = self.digital_human_platform_credential
        access_key = (getattr(credential, "client_id", "") or "").strip()
        secret_key = (getattr(credential, "client_secret", "") or "").strip()
        if not access_key or not secret_key:
            raise RuntimeError("火山即梦数字人需要配置 AccessKeyID/SecretAccessKey。")
        image_url = self._public_media_url(portrait_url) or self._public_media_url(portrait_path)
        video_url = self._public_media_url(source_video_url) or self._public_media_url(source_video_path)
        if not image_url:
            raise RuntimeError("火山即梦有参考生成需要公网可访问的头像图片 URL。")
        if not video_url:
            raise RuntimeError("火山即梦有参考生成需要公网可访问的参考视频 URL。")
        req_key = (
            self._config_note_value(self.digital_human_model_config, "req_key")
            or "pippit_iv2v_v20_cvtob_with_vinput"
        )
        app_id = self._config_note_int(self.digital_human_model_config, "app_id") or 101606596
        prompt = self._volcengine_jimeng_prompt(style_prompt)
        submit_payload = {
            "req_key": req_key,
            "app_id": app_id,
            "prompt": prompt,
            "img_url_list": [image_url],
            "video_url_list": [video_url],
        }
        task_id = await self._submit_volcengine_cv_task(api_base, access_key, secret_key, submit_payload)
        result_url = await self._poll_volcengine_cv_task(api_base, access_key, secret_key, req_key, task_id)
        return await self._download_media(result_url, "digital-human", f"{task_id}.mp4")

    def _volcengine_jimeng_prompt(self, style_prompt: str = "") -> str:
        configured = self._config_note_value(self.digital_human_model_config, "prompt")
        allow_script_prompt = self._config_note_bool(self.digital_human_model_config, "allow_script_prompt")
        if configured:
            base = configured
        elif allow_script_prompt and style_prompt:
            base = style_prompt
        else:
            base = (
                "生成一段干净的商务人物口播视频底片。人物使用参考图片中的形象，"
                "参考视频只用于坐姿、手势、镜头节奏和自然口播动作。背景真实简洁，"
                "人物面部稳定，嘴部自然，表情真实，商务专业。"
            )
        guard = (
            " 画面里绝对不要出现任何文字、字幕、标题、关键词、数字、Logo、贴纸、UI、"
            "白色大字、说明文字或屏幕文字；不要生成文字层；不要把脚本内容写在画面上。"
            " 后期字幕会由系统单独添加。"
        )
        if "不要出现任何文字" in base or "不要生成文字" in base:
            return base
        return f"{base}{guard}"

    async def _submit_volcengine_cv_task(
        self,
        api_base: str,
        access_key: str,
        secret_key: str,
        payload: dict[str, object],
    ) -> str:
        result = await self._volcengine_cv_request(
            api_base,
            access_key,
            secret_key,
            "CVSync2AsyncSubmitTask",
            payload,
            "火山即梦提交任务",
        )
        code = result.get("code")
        if code != 10000:
            raise RuntimeError(f"火山即梦提交任务失败：{result.get('message') or result}")
        task_id = self._extract_task_id(result)
        if not task_id:
            raise RuntimeError(f"火山即梦未返回 task_id：{result}")
        return task_id

    async def _poll_volcengine_cv_task(
        self,
        api_base: str,
        access_key: str,
        secret_key: str,
        req_key: str,
        task_id: str,
    ) -> str:
        query_payload = {"req_key": req_key, "task_id": task_id}
        last_result: dict[str, object] | None = None
        for _ in range(120):
            await asyncio.sleep(5)
            result = await self._volcengine_cv_request(
                api_base,
                access_key,
                secret_key,
                "CVSync2AsyncGetResult",
                query_payload,
                "火山即梦查询任务",
            )
            last_result = result
            code = result.get("code")
            if code != 10000:
                raise RuntimeError(f"火山即梦查询任务失败：{result.get('message') or result}")
            data = result.get("data") if isinstance(result.get("data"), dict) else {}
            status = str(data.get("status") or "").lower()
            if status in {"done", "succeeded", "success"}:
                video_url = self._extract_nested_media_url(data)
                if not video_url:
                    raise RuntimeError(f"火山即梦任务完成但未返回视频 URL：{result}")
                return video_url
            if status in {"failed", "fail", "error", "cancelled", "canceled"}:
                raise RuntimeError(f"火山即梦任务失败：{result.get('message') or result}")
        raise RuntimeError(f"火山即梦任务超时：{task_id}，最后状态：{last_result}")

    async def _volcengine_cv_request(
        self,
        api_base: str,
        access_key: str,
        secret_key: str,
        action: str,
        payload: dict[str, object],
        stage: str,
    ) -> dict[str, object]:
        base = (api_base or "https://visual.volcengineapi.com").rstrip("/")
        query = {"Action": action, "Version": "2022-08-31"}
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        headers = self._volcengine_signed_headers(base, query, body, access_key, secret_key)
        async with httpx.AsyncClient(timeout=240, trust_env=False) as client:
            response = await self._request_with_retries(
                client,
                "POST",
                f"{base}?{urlencode(query)}",
                stage,
                headers=headers,
                content=body,
            )
        return response.json()

    def _volcengine_signed_headers(
        self,
        api_base: str,
        query: dict[str, str],
        body: str,
        access_key: str,
        secret_key: str,
    ) -> dict[str, str]:
        parsed = urlparse(api_base)
        host = parsed.netloc
        path = parsed.path or "/"
        body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        now = datetime.now(timezone.utc)
        x_date = now.strftime("%Y%m%dT%H%M%SZ")
        short_date = now.strftime("%Y%m%d")
        region = self._config_note_value(self.digital_human_model_config, "region") or "cn-north-1"
        service = self._config_note_value(self.digital_human_model_config, "service") or "cv"
        canonical_query = self._volcengine_canonical_query(query)
        content_type = "application/json"
        signed_headers = "content-type;host;x-content-sha256;x-date"
        canonical_headers = (
            f"content-type:{content_type}\n"
            f"host:{host}\n"
            f"x-content-sha256:{body_hash}\n"
            f"x-date:{x_date}\n"
        )
        canonical_request = "\n".join(
            ["POST", path, canonical_query, canonical_headers, signed_headers, body_hash]
        )
        credential_scope = f"{short_date}/{region}/{service}/request"
        string_to_sign = "\n".join(
            [
                "HMAC-SHA256",
                x_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signing_key = self._volcengine_signing_key(secret_key, short_date, region, service)
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        authorization = (
            f"HMAC-SHA256 Credential={access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        return {
            "Authorization": authorization,
            "Content-Type": content_type,
            "Host": host,
            "X-Content-Sha256": body_hash,
            "X-Date": x_date,
        }

    def _volcengine_signing_key(self, secret_key: str, short_date: str, region: str, service: str) -> bytes:
        date_key = hmac.new(secret_key.encode("utf-8"), short_date.encode("utf-8"), hashlib.sha256).digest()
        region_key = hmac.new(date_key, region.encode("utf-8"), hashlib.sha256).digest()
        service_key = hmac.new(region_key, service.encode("utf-8"), hashlib.sha256).digest()
        return hmac.new(service_key, b"request", hashlib.sha256).digest()

    def _volcengine_canonical_query(self, query: dict[str, str]) -> str:
        items = []
        for key in sorted(query):
            value = query[key]
            if isinstance(value, list):
                for item in value:
                    items.append(f"{quote(str(key), safe='-_.~')}={quote(str(item), safe='-_.~')}")
            else:
                items.append(f"{quote(str(key), safe='-_.~')}={quote(str(value), safe='-_.~')}")
        return "&".join(items).replace("+", "%20")

    async def _submit_aliyun_video_synthesis_task(
        self,
        api_base: str,
        api_key: str,
        model: str,
        input_payload: dict[str, object],
        parameters: dict[str, object],
    ) -> str:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }
        payload = {"model": model, "input": input_payload}
        if parameters:
            payload["parameters"] = parameters
        async with httpx.AsyncClient(timeout=300, trust_env=False) as client:
            response = await client.post(
                self._aliyun_video_synthesis_endpoint(api_base),
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        task_id = self._extract_task_id(data)
        if not task_id:
            raise RuntimeError(f"阿里云数字人未返回 task_id：{data}")
        return task_id

    async def _poll_aliyun_video_synthesis_task(self, api_base: str, api_key: str, task_id: str) -> str:
        headers = {"Authorization": f"Bearer {api_key}"}
        async with httpx.AsyncClient(timeout=300, trust_env=False) as client:
            for _ in range(180):
                await asyncio.sleep(5)
                response = await client.get(self._aliyun_task_endpoint(api_base, task_id), headers=headers)
                response.raise_for_status()
                data = response.json()
                status = self._aliyun_task_status(data)
                if status in {"succeeded", "success", "done"}:
                    video_url = self._extract_nested_media_url(data)
                    if video_url:
                        return video_url
                    raise RuntimeError(f"阿里云数字人任务成功但未返回视频地址：{data}")
                if status in {"failed", "fail", "error", "canceled", "cancelled"}:
                    raise RuntimeError(f"阿里云数字人生成失败：{data.get('message') or data.get('error') or data}")
        raise RuntimeError(f"阿里云数字人生成超时：{task_id}")

    async def _generate_did_talk(
        self,
        portrait_path: Optional[str],
        audio_path: str,
        api_base: str,
        api_key: Optional[str],
        style_prompt: str = "",
    ) -> str:
        if not portrait_path or not self._is_local_path(portrait_path) or not Path(portrait_path).exists():
            raise RuntimeError("D-ID 数字人需要本地头像图片")
        if not self._is_local_path(audio_path) or not Path(audio_path).exists():
            raise RuntimeError("D-ID 数字人需要本地音频文件")
        if not api_key:
            raise RuntimeError("D-ID API Key 未配置")

        base = api_base.rstrip("/")
        headers = self._did_headers(api_key)
        image_url = await self._did_upload_file(
            f"{base}/images",
            "image",
            portrait_path,
            headers,
        )
        audio_url = self._audio_source_url(audio_path)
        if not audio_url:
            audio_url = await self._did_upload_file(
                f"{base}/audios",
                "audio",
                audio_path,
                headers,
            )
        payload = {
            "source_url": image_url,
            "script": {
                "type": "audio",
                "audio_url": audio_url,
            },
            "config": {
                "stitch": True,
                "fluent": True,
            },
        }
        async with httpx.AsyncClient(timeout=300, trust_env=False) as client:
            create_response = await client.post(f"{base}/talks", headers={**headers, "Content-Type": "application/json"}, json=payload)
            create_response.raise_for_status()
            talk_data = create_response.json()

            immediate_url = self._did_result_url(talk_data)
            if immediate_url.startswith("http"):
                return await self._download_media(immediate_url, "digital-human", "talking-avatar.mp4")

            talk_id = str(talk_data.get("id") or "")
            if not talk_id:
                raise RuntimeError("D-ID 创建任务未返回 talk id")
            for _ in range(120):
                await asyncio.sleep(3)
                status_response = await client.get(f"{base}/talks/{talk_id}", headers=headers)
                status_response.raise_for_status()
                status_data = status_response.json()
                status = str(status_data.get("status") or "").lower()
                result_url = self._did_result_url(status_data)
                if result_url.startswith("http") and status in {"done", "created"}:
                    return await self._download_media(result_url, "digital-human", "talking-avatar.mp4")
                if status in {"error", "failed", "rejected"}:
                    raise RuntimeError(f"D-ID 数字人生成失败：{status_data.get('error') or status_data}")
            raise RuntimeError(f"D-ID 数字人生成超时：{talk_id}")

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
        async with httpx.AsyncClient(timeout=900, trust_env=False) as client:
            response = await client.post(url, data=data, files=files, headers=headers)
            response.raise_for_status()
            if response.headers.get("content-type", "").startswith("video/"):
                output_path = self._asset_path("digital-human", "talking-avatar.mp4")
                output_path.write_bytes(response.content)
                return {"path": str(output_path)}
            return response.json()

    async def _request_with_retries(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        stage: str,
        attempts: int = 3,
        **kwargs,
    ) -> httpx.Response:
        for attempt in range(attempts):
            try:
                response = await client.request(method, url, **kwargs)
                if response.status_code >= 500 and attempt < attempts - 1:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text[:500]
                raise RuntimeError(f"{stage} HTTP {exc.response.status_code}: {detail}") from exc
            except httpx.TransportError as exc:
                if attempt >= attempts - 1:
                    raise RuntimeError(f"{stage}连接失败：{exc}") from exc
                await asyncio.sleep(2 * (attempt + 1))
        raise RuntimeError(f"{stage}请求失败")

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
        async with httpx.AsyncClient(timeout=180, trust_env=False) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            if binary:
                return response.content
            return response.json()

    async def _generate_seedance_clip_via_ark(
        self,
        prompt: str,
        duration_seconds: int = 5,
        export_profile: str | None = None,
        reference_media: list[dict[str, object]] | None = None,
    ) -> str:
        config = self.video_model_config
        api_base = config.api_base if config and config.api_base else self.settings.seedance_api_base
        api_key = config.api_key if config and config.api_key else self.settings.seedance_api_key
        model_name = config.model_name if config and config.model_name else self.settings.seedance_model
        if not api_base:
            api_base = "https://ark.cn-beijing.volces.com/api/v3"
        if not api_key:
            raise RuntimeError("Seedance API Key 未配置，无法生成真实视频。")

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = self._seedance_request_payload(
            model_name,
            prompt,
            duration_seconds,
            export_profile,
            reference_media,
        )
        async with httpx.AsyncClient(timeout=180, trust_env=False) as client:
            async def seedance_request(method: str, url: str, stage: str, **kwargs) -> httpx.Response:
                for attempt in range(3):
                    try:
                        response = await client.request(method, url, **kwargs)
                        if response.status_code >= 500 and attempt < 2:
                            await asyncio.sleep(2 * (attempt + 1))
                            continue
                        response.raise_for_status()
                        return response
                    except httpx.HTTPStatusError as exc:
                        detail = exc.response.text[:500]
                        raise RuntimeError(f"Seedance {stage} HTTP {exc.response.status_code}: {detail}") from exc
                    except httpx.TransportError as exc:
                        if attempt >= 2:
                            raise RuntimeError(f"Seedance {stage} 连接失败：{exc}") from exc
                        await asyncio.sleep(2 * (attempt + 1))
                raise RuntimeError(f"Seedance {stage} 请求失败")

            response = await seedance_request(
                "POST",
                api_base.rstrip("/") + "/contents/generations/tasks",
                "创建任务",
                headers=headers,
                json=payload,
            )
            task_id = response.json().get("id")
            if not task_id:
                raise RuntimeError("Seedance task id not returned")

            task_data = None
            query_url = api_base.rstrip("/") + f"/contents/generations/tasks/{task_id}"
            for _ in range(120):
                await asyncio.sleep(5)
                task_response = await seedance_request("GET", query_url, "查询任务", headers=headers)
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
            video_response = await seedance_request("GET", video_url, "下载视频", timeout=180)

        output_path = self._asset_path("seedance", f"{task_id}.mp4")
        output_path.write_bytes(video_response.content)
        return str(output_path)

    async def _download_media(self, url: str, category: str, filename: str) -> str:
        async with httpx.AsyncClient(timeout=300, trust_env=False) as client:
            response = await self._request_with_retries(client, "GET", url, f"{category} 媒体下载")
        output_path = self._asset_path(category, filename)
        output_path.write_bytes(response.content)
        return str(output_path)

    def _media_duration_seconds(self, media_path: Optional[str]) -> Optional[float]:
        if not media_path or not self._is_local_path(media_path):
            return None
        path = Path(media_path)
        if not path.exists():
            return None
        if path.suffix.lower() == ".wav":
            try:
                with wave.open(str(path), "rb") as source:
                    frames = source.getnframes()
                    rate = source.getframerate()
                    channels = source.getnchannels() or 1
                    sample_width = source.getsampwidth() or 2
                    header_duration = frames / float(rate) if rate else None
                    data_bytes = max(0, path.stat().st_size - 44)
                    size_duration = data_bytes / float(rate * channels * sample_width) if rate else None
                    if header_duration and size_duration and header_duration > size_duration * 5:
                        return size_duration
                    return header_duration
            except (wave.Error, OSError):
                return None
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            )
            return float(result.stdout.strip())
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
            return None

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
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
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

    def _export_to_profile(self, input_path: str, export_profile: str | None = None) -> str:
        if not export_profile or not self._is_local_path(input_path):
            return input_path
        source_path = Path(input_path)
        if not source_path.exists() or not source_path.is_file():
            return input_path

        from moviepy.editor import VideoClip, VideoFileClip
        from PIL import Image, ImageEnhance, ImageFilter
        import numpy as np

        profile = resolve_export_profile(export_profile)
        output_path = self._asset_path("final", f"{profile.key}.mp4")
        source = VideoFileClip(str(source_path))
        target_size = (profile.width, profile.height)
        if source.w == profile.width and source.h == profile.height:
            source.close()
            return input_path

        fps = max(20, min(30, int(getattr(source, "fps", 24) or 24)))

        def cover_frame(image: Image.Image) -> Image.Image:
            scale = max(profile.width / image.width, profile.height / image.height)
            resized = image.resize((int(image.width * scale), int(image.height * scale)), Image.Resampling.LANCZOS)
            left = max(0, (resized.width - profile.width) // 2)
            top = max(0, (resized.height - profile.height) // 2)
            return resized.crop((left, top, left + profile.width, top + profile.height))

        def contain_blur_frame(image: Image.Image) -> Image.Image:
            background = cover_frame(image).filter(ImageFilter.GaussianBlur(radius=28))
            background = ImageEnhance.Brightness(background).enhance(0.58)
            scale = min(profile.width / image.width, profile.height / image.height)
            foreground = image.resize((int(image.width * scale), int(image.height * scale)), Image.Resampling.LANCZOS)
            canvas = background.convert("RGBA")
            x = (profile.width - foreground.width) // 2
            y = (profile.height - foreground.height) // 2
            canvas.paste(foreground, (x, y))
            return canvas.convert("RGB")

        def make_frame(t: float):
            frame = Image.fromarray(source.get_frame(min(t, source.duration - 0.05))).convert("RGB")
            image = cover_frame(frame) if profile.fit_mode == "crop" else contain_blur_frame(frame)
            return np.array(image.convert("RGB"))

        exported = VideoClip(make_frame, duration=source.duration)
        if source.audio is not None:
            exported = exported.set_audio(source.audio)
        try:
            exported.write_videofile(
                str(output_path),
                fps=fps,
                codec="libx264",
                audio_codec="aac",
                preset="medium",
                bitrate="5200k" if profile.width >= 1080 else "3500k",
                threads=4,
                ffmpeg_params=["-movflags", "+faststart"],
                verbose=False,
                logger=None,
            )
        finally:
            exported.close()
            source.close()
        return str(output_path)

    def _asset_path(self, category: str, filename: str) -> Path:
        folder = self.storage_dir / category / uuid4().hex
        folder.mkdir(parents=True, exist_ok=True)
        return folder / filename

    def prepare_segment_audio_reference(
        self,
        audio_path: str,
        start_seconds: float,
        duration_seconds: int,
    ) -> tuple[str, str] | None:
        if not self.settings.app_public_base_url or not self._is_local_path(audio_path):
            return None
        source = Path(audio_path)
        if not source.exists():
            return None
        output_path = self._asset_path("generation-inputs", "speech.wav")
        command = [
            self.settings.ffmpeg_binary,
            "-y",
            "-ss",
            str(max(0.0, start_seconds)),
            "-t",
            str(max(1, duration_seconds)),
            "-i",
            str(source),
            "-ac",
            "1",
            "-ar",
            "44100",
            str(output_path),
        ]
        subprocess.run(command, check=True, capture_output=True)
        return str(output_path), self._generation_input_url(output_path)

    def cleanup_generation_inputs(self, paths: list[str]) -> None:
        for value in paths:
            path = Path(value)
            path.unlink(missing_ok=True)
            try:
                path.parent.rmdir()
            except OSError:
                pass

    def _generation_input_url(self, path: Path) -> str:
        root = (self.storage_dir / "generation-inputs").resolve()
        relative = path.resolve().relative_to(root).as_posix()
        return f"{str(self.settings.app_public_base_url).rstrip('/')}/generation-inputs/{quote(relative, safe='/')}"

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

    def _seedance_prompt(
        self,
        prompt: str,
        duration_seconds: int = 5,
        export_profile: str | None = None,
    ) -> str:
        del duration_seconds, export_profile
        return re.sub(r"\s*--(?:ratio|resolution|dur|fps)\s+\S+", "", prompt).strip()

    def _seedance_request_payload(
        self,
        model_name: str,
        prompt: str,
        duration_seconds: int,
        export_profile: str | None,
        reference_media: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        profile = resolve_export_profile(export_profile)
        normalized_model = model_name.lower()
        supports_1080p = "fast" not in normalized_model and "mini" not in normalized_model
        resolution = "1080p" if supports_1080p and max(profile.width, profile.height) >= 1920 else "720p"
        return {
            "model": model_name,
            "content": self._seedance_content(prompt, duration_seconds, export_profile, reference_media),
            "duration": max(4, min(15, int(round(duration_seconds)))),
            "ratio": profile.generation_ratio,
            "resolution": resolution,
            "generate_audio": False,
            "watermark": False,
        }

    def _seedance_content(
        self,
        prompt: str,
        duration_seconds: int = 5,
        export_profile: str | None = None,
        reference_media: list[dict[str, object]] | None = None,
    ) -> list[dict[str, object]]:
        content: list[dict[str, object]] = [
            {"type": "text", "text": self._seedance_prompt(prompt, duration_seconds, export_profile)}
        ]
        for item in reference_media or []:
            media = self._seedance_reference_content_item(item)
            if media:
                content.append(media)
        return content

    def _seedance_reference_content_item(self, item: dict[str, object]) -> dict[str, object] | None:
        source_url = str(item.get("source_url") or "").strip()
        file_path = str(item.get("file_path") or "").strip()
        kind = str(item.get("kind") or "").lower()
        role = str(item.get("role") or "reference_image")
        if source_url.startswith("asset://"):
            return {"type": "image_url", "image_url": {"url": source_url}, "role": role}
        media_url = self._public_media_url(source_url) or self._public_media_url(file_path)
        if not media_url:
            return None

        mime_type = mimetypes.guess_type(media_url)[0] or mimetypes.guess_type(file_path)[0] or ""
        if kind in {"image", "portrait", "product"} or mime_type.startswith("image/"):
            return {"type": "image_url", "image_url": {"url": media_url}, "role": role}
        if kind in {"video", "reference", "avatar_source"} or mime_type.startswith("video/"):
            return {"type": "video_url", "video_url": {"url": media_url}, "role": "reference_video"}
        if mime_type.startswith("audio/"):
            return {"type": "audio_url", "audio_url": {"url": media_url}, "role": "reference_audio"}
        return None

    def _seedance_video_url(self, task_data: dict[str, object]) -> Optional[str]:
        content = task_data.get("content")
        if isinstance(content, dict):
            for key in ("video_url", "url", "output_url"):
                value = content.get(key)
                if isinstance(value, str) and value:
                    return value
        return None

    def _is_dashscope_tts(self, provider: str, api_base: Optional[str]) -> bool:
        normalized_provider = (provider or "").lower()
        normalized_base = (api_base or "").lower()
        return normalized_provider in DASHSCOPE_TTS_PROVIDERS or "dashscope.aliyuncs.com" in normalized_base

    def _is_dashscope_voice_clone(self, provider: str, api_base: Optional[str]) -> bool:
        normalized_provider = (provider or "").lower()
        normalized_base = (api_base or "").lower()
        return normalized_provider in DASHSCOPE_VOICE_CLONE_PROVIDERS or (
            normalized_provider == "cosyvoice-clone" and "dashscope.aliyuncs.com" in normalized_base
        )

    def _is_did_provider(self, provider: str) -> bool:
        return (provider or "").lower() in DID_DIGITAL_HUMAN_PROVIDERS

    def _is_aliyun_digital_human_provider(self, provider: str) -> bool:
        normalized_provider = (provider or "").lower()
        return normalized_provider in ALIYUN_DIGITAL_HUMAN_PROVIDERS

    def _is_aliyun_liveportrait(self, provider: str, model_name: str) -> bool:
        value = f"{provider} {model_name}".lower()
        return "liveportrait" in value

    def _is_aliyun_videoretalk(self, provider: str, model_name: str) -> bool:
        value = f"{provider} {model_name}".lower()
        return "videoretalk" in value

    def _is_volcengine_jimeng_provider(self, provider: str) -> bool:
        value = (provider or "").lower()
        return value in {"volcengine-jimeng-digital-human", "jimeng-digital-human"} or (
            "jimeng" in value and "digital" in value
        )

    def _aliyun_video_synthesis_endpoint(self, api_base: str) -> str:
        base = api_base.rstrip("/")
        if base.endswith("/video-synthesis"):
            return f"{base}/"
        if base.endswith("/video-synthesis/"):
            return base
        if base.endswith("/api/v1"):
            return f"{base}/services/aigc/image2video/video-synthesis/"
        return f"{base}/api/v1/services/aigc/image2video/video-synthesis/"

    def _aliyun_task_endpoint(self, api_base: str, task_id: str) -> str:
        base = api_base.rstrip("/")
        if "/api/v1/services/" in base:
            base = base.split("/api/v1/services/", 1)[0] + "/api/v1"
        elif not base.endswith("/api/v1"):
            base = f"{base}/api/v1"
        return f"{base}/tasks/{task_id}"

    def _dashscope_tts_endpoint(self, api_base: str) -> str:
        base = api_base.rstrip("/")
        if base.endswith("/SpeechSynthesizer"):
            return base
        if base.endswith("/api/v1"):
            return f"{base}/services/audio/tts/SpeechSynthesizer"
        return f"{base}/api/v1/services/audio/tts/SpeechSynthesizer"

    def _dashscope_customization_endpoint(self, api_base: str) -> str:
        base = api_base.rstrip("/")
        if base.endswith("/customization"):
            return base
        if base.endswith("/api/v1"):
            return f"{base}/services/audio/tts/customization"
        return f"{base}/api/v1/services/audio/tts/customization"

    def _config_note_value(self, model_config, key: str) -> Optional[str]:
        if not model_config or not getattr(model_config, "notes", ""):
            return None
        notes = str(model_config.notes).strip()
        try:
            parsed = json.loads(notes)
            if isinstance(parsed, dict):
                value = parsed.get(key)
                return str(value).strip() if value else None
        except json.JSONDecodeError:
            pass
        for line in notes.splitlines():
            if "=" not in line:
                continue
            item_key, item_value = line.split("=", 1)
            if item_key.strip() == key:
                return item_value.strip() or None
        return None

    def _config_note_bool(self, model_config, key: str) -> bool:
        value = self._config_note_value(model_config, key)
        return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enable", "enabled"}

    def _config_note_int(self, model_config, key: str) -> Optional[int]:
        value = self._config_note_value(model_config, key)
        if value is None:
            return None
        try:
            return int(float(value))
        except ValueError:
            return None

    def _config_note_float(self, model_config, key: str) -> Optional[float]:
        value = self._config_note_value(model_config, key)
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    def _nested_value(self, data: object, path: tuple[str, ...]) -> object:
        current = data
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    def _extract_task_id(self, data: object) -> Optional[str]:
        for key in ("task_id", "id"):
            value = self._nested_value(data, (key,))
            if isinstance(value, str) and value:
                return value
        for path in (("output", "task_id"), ("data", "task_id"), ("result", "task_id")):
            value = self._nested_value(data, path)
            if isinstance(value, str) and value:
                return value
        return None

    def _aliyun_task_status(self, data: object) -> str:
        for path in (("output", "task_status"), ("output", "status"), ("task_status",), ("status",), ("data", "status")):
            value = self._nested_value(data, path)
            if isinstance(value, str) and value:
                return value.lower()
        return ""

    def _extract_nested_media_url(self, data: object) -> str:
        if isinstance(data, str):
            return data if data.startswith(("http://", "https://")) else ""
        if isinstance(data, list):
            for item in data:
                url = self._extract_nested_media_url(item)
                if url:
                    return url
            return ""
        if not isinstance(data, dict):
            return ""
        for key in (
            "video_url",
            "url",
            "result_url",
            "output_url",
            "file_url",
            "download_url",
            "orig_video_url",
        ):
            value = data.get(key)
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                return value
        for key in ("output", "data", "result", "results", "video", "videos"):
            url = self._extract_nested_media_url(data.get(key))
            if url:
                return url
        return ""

    def _public_media_url(self, value: Optional[str]) -> Optional[str]:
        if value and value.startswith(("http://", "https://")):
            return value
        return None

    def _voice_prefix(self, speaker_name: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9_]", "", (speaker_name or "").lower())
        if not cleaned:
            cleaned = "voice"
        return f"{cleaned[:10]}{uuid4().hex[:4]}"

    def _did_headers(self, api_key: str) -> dict[str, str]:
        cleaned = api_key.strip()
        if cleaned.lower().startswith(("basic ", "bearer ")):
            return {"Authorization": cleaned}
        return {"Authorization": f"Basic {cleaned}"}

    async def _did_upload_file(
        self,
        url: str,
        field_name: str,
        file_path: str,
        headers: dict[str, str],
    ) -> str:
        path = Path(file_path)
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with open(path, "rb") as upload_file:
            files = {
                field_name: (path.name, upload_file, mime_type),
            }
            async with httpx.AsyncClient(timeout=300, trust_env=False) as client:
                response = await client.post(url, headers=headers, files=files)
                response.raise_for_status()
                data = response.json()
        media_url = self._extract_media_url(data, field_name)
        if not media_url.startswith("http"):
            raise RuntimeError(f"D-ID 上传 {field_name} 后未返回可访问 URL")
        return media_url

    def _audio_source_url(self, audio_path: str) -> Optional[str]:
        sidecar = Path(f"{audio_path}.source_url")
        if sidecar.exists():
            url = sidecar.read_text(encoding="utf-8").strip()
            if url.startswith(("http://", "https://")):
                return url
        return None

    def _did_result_url(self, data: dict[str, object]) -> str:
        for key in ("result_url", "video_url", "output_url"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
        result = data.get("result")
        if isinstance(result, dict):
            return self._did_result_url(result)
        return ""

    def _mock_asset(self, category: str, filename: str) -> str:
        return f"mock://{category}/{filename}"

    def _extract_media_url(self, result: dict[str, object], fallback_key: str) -> str:
        for key in ("url", "result_url", "video_url", "audio_url", "image_url", "source_url", "output_url", "path", "output_path"):
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
        for nested_key in ("output", "data", "result"):
            data = result.get(nested_key)
            if isinstance(data, dict):
                voice_id = self._extract_voice_id(data)
                if voice_id:
                    return voice_id
        return None

    def _is_local_path(self, value: str) -> bool:
        return bool(value) and not value.startswith("mock://") and not value.startswith("http")
