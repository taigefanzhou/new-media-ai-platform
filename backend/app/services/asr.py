from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import httpx
from app.core.config import get_settings
from app.models.entities import Material, TranscriptionTask


@dataclass
class TranscriptionResult:
    transcript: str
    summary: str
    hook_analysis: str


class ASRClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def transcribe(self, task: TranscriptionTask, material: Material) -> TranscriptionResult:
        if self.settings.asr_provider in ("volcengine", "http-json") and self.settings.asr_api_base:
            return await self._transcribe_http_json(task, material)
        return self._mock_result(material)

    async def _transcribe_http_json(self, task: TranscriptionTask, material: Material) -> TranscriptionResult:
        headers = {}
        if self.settings.asr_api_key:
            headers["Authorization"] = f"Bearer {self.settings.asr_api_key}"

        payload = {
            "model": self.settings.asr_model,
            "language": task.language,
            "file_path": material.file_path,
            "source_url": material.source_url,
            "material_name": material.name,
        }
        url = self.settings.asr_api_base.rstrip("/") + "/asr/transcriptions"
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        transcript = self._extract_text(data)
        return TranscriptionResult(
            transcript=transcript,
            summary=self._extract_field(data, "summary") or "已完成转写，等待 AI 做结构分析。",
            hook_analysis=self._extract_field(data, "hook_analysis") or "可根据前三句话提炼开头钩子。",
        )

    def _mock_result(self, material: Material) -> TranscriptionResult:
        transcript = (
            f"这是素材《{material.name}》的示例转写文本。"
            "开头先提出一个强痛点：为什么企业短视频做了很多条，却没有稳定获客。"
            "中间拆解三个原因：选题不聚焦、脚本没有转化路径、发布后没有数据复盘。"
            "结尾给出解决方案：用数字人建立标准化内容生产流程。"
        )
        return TranscriptionResult(
            transcript=transcript,
            summary="参考内容结构为：痛点开场、原因拆解、解决方案、行动引导。",
            hook_analysis="开头钩子适合改写为：为什么你的企业短视频一直有播放却没客户？",
        )

    def _extract_text(self, data: Any) -> str:
        if isinstance(data, str):
            return data
        if not isinstance(data, dict):
            return ""
        for key in ("text", "transcript", "result", "content"):
            value = data.get(key)
            if isinstance(value, str):
                return value
        for key in ("data", "utterances", "segments"):
            value = data.get(key)
            if isinstance(value, dict):
                text = self._extract_text(value)
                if text:
                    return text
            if isinstance(value, list):
                parts = []
                for item in value:
                    text = self._extract_text(item)
                    if text:
                        parts.append(text)
                if parts:
                    return "\n".join(parts)
        return ""

    def _extract_field(self, data: Any, key: str) -> str:
        if isinstance(data, dict):
            value = data.get(key)
            if isinstance(value, str):
                return value
        return ""
