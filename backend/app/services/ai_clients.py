from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
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
    def __init__(self) -> None:
        self.settings = get_settings()

    async def generate(
        self,
        topic: str,
        brand_voice: str,
        duration_seconds: int,
        target_platform: str,
    ) -> GeneratedScript:
        if self.settings.llm_provider == "stub":
            return self._stub(topic, brand_voice, duration_seconds, target_platform)
        return self._stub(topic, brand_voice, duration_seconds, target_platform)

    def _stub(
        self,
        topic: str,
        brand_voice: str,
        duration_seconds: int,
        target_platform: str,
    ) -> GeneratedScript:
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
    async def synthesize_voice(self, text: str, voice: Optional[str] = None) -> str:
        return "mock://voice/voiceover.wav"

    async def generate_talking_avatar(self, portrait_path: Optional[str], audio_path: str) -> str:
        return "mock://digital-human/talking-avatar.mp4"

    async def generate_seedance_clips(self, prompt: str) -> list[str]:
        return ["mock://seedance/clip-1.mp4", "mock://seedance/clip-2.mp4"]

    async def compose_final_video(self, clips: list[str], avatar_clip: str) -> str:
        return "mock://final/final-video.mp4"
