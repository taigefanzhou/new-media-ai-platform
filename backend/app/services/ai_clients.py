from __future__ import annotations

import json
import subprocess
import asyncio
from pathlib import Path
from dataclasses import dataclass
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
            "requirements": [
                "如果 output_language 是 en-US，所有 hook、voiceover、title_options、hashtags、compliance_notes 必须使用英文；否则使用中文",
                "不要复刻或搬运任何参考视频原文",
                "适合公司新媒体账号和数字人口播",
                "分镜要能转成 Seedance 视频提示词；seedance_prompt 始终使用英文",
                "必须输出严格 JSON",
            ],
            "json_schema": {
                "hook": "开头钩子，一句话",
                "voiceover": "完整口播稿",
                "storyboard": "按镜头分行的分镜",
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

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return GeneratedScript(
            hook=parsed.get("hook", ""),
            voiceover=parsed.get("voiceover", ""),
            storyboard=parsed.get("storyboard", ""),
            seedance_prompt=parsed.get("seedance_prompt", ""),
            title_options=parsed.get("title_options", ""),
            hashtags=parsed.get("hashtags", ""),
            compliance_notes=parsed.get("compliance_notes", ""),
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
            return GeneratedScript(
                hook=f"The real value of {topic} is not convenience alone, but smarter hotel operations.",
                voiceover=(
                    f"In {duration_seconds} seconds, here is why a smart no-card power solution matters for hotels. "
                    "Guests no longer need to insert a room card to use electricity, so the check-in experience feels smoother. "
                    "When guests leave the room, the system can automatically reduce unnecessary power consumption from lights and air conditioning. "
                    "It also connects room status, energy data, and hotel operations, helping hotels improve guest experience while lowering operating costs."
                ),
                storyboard=(
                    "Shot 1: A premium hotel room entrance with a smart power control panel.\n"
                    "Shot 2: Warm lights turn on automatically as the guest enters.\n"
                    "Shot 3: Energy usage dashboard shows reduced waste after checkout.\n"
                    "Shot 4: Clean hotel room atmosphere with a concise business-style ending."
                ),
                seedance_prompt=(
                    "Vertical 9:16 modern business hotel technology video, smart no-card power control panel, "
                    "warm lights turning on automatically, premium hotel room, close-up shot, slow cinematic camera movement, "
                    "no people, no logos, no readable text."
                ),
                title_options=(
                    "1. Smarter Hotel Energy Control\n"
                    "2. No-Card Power Solution for Modern Hotels\n"
                    "3. Better Guest Experience, Lower Energy Waste"
                ),
                hashtags="#HotelTech #SmartHotel #EnergySaving #Hospitality",
                compliance_notes="Use only licensed visuals and verify that all product claims are accurate before publishing.",
            )
        return GeneratedScript(
            hook=f"你有没有发现，{topic}真正影响结果的不是选择多，而是判断标准。",
            voiceover=(
                f"今天用{duration_seconds}秒讲清楚：{topic}。"
                "第一，先看真实需求；第二，比较关键指标；第三，选择能持续交付的方案。"
                "我们把复杂信息拆成可执行步骤，让客户少走弯路，快速做决定。"
            ),
            storyboard=(
                "镜头1：数字人正面开场，提出痛点。\n"
                "镜头2：展示产品/服务场景，字幕强调关键指标。\n"
                "镜头3：对比常见误区和正确做法。\n"
                "镜头4：数字人总结并引导咨询。"
            ),
            seedance_prompt=(
                "Vertical 9:16 corporate short video, clean modern office, confident presenter, "
                "product explanation shots, smooth camera movement, professional lighting, no logos from other brands."
            ),
            title_options=(
                f"1. {topic}怎么选？看这3点\n"
                f"2. 别再盲选{topic}了\n"
                f"3. {topic}的关键判断标准"
            ),
            hashtags=f"#{target_platform} #企业服务 #数字人 #短视频运营",
            compliance_notes="外部素材只可作为选题参考；成片需人工确认无侵权、无夸大承诺。",
        )


class MediaGenerationClient:
    def __init__(self, video_model_config=None) -> None:
        self.settings = get_settings()
        self.video_model_config = video_model_config
        self.storage_dir = Path(self.settings.storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    async def synthesize_voice(self, text: str, voice: Optional[str] = None) -> str:
        if self.settings.tts_provider == "mock" or not self.settings.tts_api_base:
            return self._mock_asset("voice", "voiceover.wav")

        payload = {
            "text": text,
            "voice": voice or self.settings.tts_voice,
            "format": "wav",
        }
        data = await self._post_media(
            self.settings.tts_api_base,
            "/synthesize",
            payload,
            api_key=self.settings.tts_api_key,
            binary=True,
        )
        output_path = self._asset_path("voice", "voiceover.wav")
        output_path.write_bytes(data)
        return str(output_path)

    async def generate_talking_avatar(self, portrait_path: Optional[str], audio_path: str) -> str:
        if self.settings.digital_human_provider == "mock" or not self.settings.digital_human_api_base:
            return self._mock_asset("digital-human", "talking-avatar.mp4")

        payload = {
            "provider": self.settings.digital_human_provider,
            "portrait_path": portrait_path,
            "audio_path": audio_path,
            "format": "mp4",
        }
        result = await self._post_media(
            self.settings.digital_human_api_base,
            "/generate",
            payload,
            api_key=self.settings.digital_human_api_key,
        )
        return self._extract_media_url(result, "digital_human_video")

    async def generate_seedance_clips(self, prompt: str) -> list[str]:
        if self.video_model_config and self.video_model_config.provider == "seedance":
            return [await self._generate_seedance_clip_via_ark(prompt)]

        provider = self.settings.video_generation_provider
        if provider == "seedance" and self.settings.seedance_api_base:
            return [await self._generate_seedance_clip_via_ark(prompt)]

        if provider == "comfyui" and self.settings.comfyui_api_base:
            payload = {"prompt": prompt, "workflow": "default-video-generation"}
            result = await self._post_media(self.settings.comfyui_api_base, "/prompt", payload)
            return [self._extract_media_url(result, "comfyui_job")]

        return [
            self._mock_asset("seedance", "clip-1.mp4"),
            self._mock_asset("seedance", "clip-2.mp4"),
        ]

    async def compose_final_video(self, clips: list[str], avatar_clip: str) -> str:
        if self.settings.composition_provider != "ffmpeg":
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

    async def _generate_seedance_clip_via_ark(self, prompt: str) -> str:
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
            "content": [{"type": "text", "text": self._seedance_prompt(prompt)}],
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

    def _asset_path(self, category: str, filename: str) -> Path:
        folder = self.storage_dir / category / uuid4().hex
        folder.mkdir(parents=True, exist_ok=True)
        return folder / filename

    def _seedance_prompt(self, prompt: str) -> str:
        controls = "--ratio 9:16 --resolution 480p --dur 5 --fps 24"
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

    def _is_local_path(self, value: str) -> bool:
        return bool(value) and not value.startswith("mock://") and not value.startswith("http")
