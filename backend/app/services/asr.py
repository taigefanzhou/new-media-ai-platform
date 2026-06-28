from __future__ import annotations

import base64
from dataclasses import dataclass
import mimetypes
from pathlib import Path
import subprocess
from typing import Any
import httpx
from app.core.config import get_settings
from app.models.entities import AIModelConfig, Material, TranscriptionTask

HTTP_JSON_ASR_PROVIDERS = {"aliyun-bailian", "http-json", "openai-compatible", "volcengine", "whisperx"}
KEYLESS_ASR_PROVIDERS = {"http-json", "whisperx"}
QWEN_ASR_PROVIDERS = {"aliyun-bailian", "qwen-asr"}
QWEN_ASR_BASE64_MAX_BYTES = 7_500_000
QWEN_ASR_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
QWEN_ASR_MEDIA_EXTENSIONS = QWEN_ASR_VIDEO_EXTENSIONS | {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg"}


@dataclass
class TranscriptionResult:
    transcript: str
    summary: str
    hook_analysis: str


class ASRClient:
    def __init__(self, model_config: AIModelConfig | None = None) -> None:
        self.settings = get_settings()
        self.model_config = model_config

    async def transcribe(self, task: TranscriptionTask, material: Material) -> TranscriptionResult:
        provider = self.model_config.provider if self.model_config else self.settings.asr_provider
        api_base = self.model_config.api_base if self.model_config and self.model_config.api_base else self.settings.asr_api_base
        api_key = self.model_config.api_key if self.model_config and self.model_config.api_key else self.settings.asr_api_key
        model_name = self.model_config.model_name if self.model_config else self.settings.asr_model
        if provider in ("mock", "local"):
            return self._mock_result(material)
        if self._is_qwen_asr(provider, model_name):
            if not api_base:
                raise RuntimeError("Qwen-ASR 接口地址未配置，请使用 https://dashscope.aliyuncs.com/compatible-mode/v1")
            if not api_key:
                raise RuntimeError("Qwen-ASR API Key 未配置")
            return await self._transcribe_qwen_asr(task, material, api_base, api_key, model_name)
        if provider in HTTP_JSON_ASR_PROVIDERS:
            if not api_base:
                raise RuntimeError("ASR service API base is not configured")
            if not api_key and provider not in KEYLESS_ASR_PROVIDERS:
                raise RuntimeError("ASR service API key is not configured")
            return await self._transcribe_http_json(task, material, api_base, api_key, model_name)
        return self._mock_result(material)

    async def _transcribe_http_json(
        self,
        task: TranscriptionTask,
        material: Material,
        api_base: str,
        api_key: str | None,
        model_name: str,
    ) -> TranscriptionResult:
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model_name,
            "language": task.language,
            "file_path": material.file_path,
            "source_url": material.source_url,
            "material_name": material.name,
        }
        url = api_base.rstrip("/") + "/asr/transcriptions"
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

    async def _transcribe_qwen_asr(
        self,
        task: TranscriptionTask,
        material: Material,
        api_base: str,
        api_key: str,
        model_name: str,
    ) -> TranscriptionResult:
        audio_data = self._qwen_audio_input(material)
        asr_options: dict[str, object] = {"enable_itn": True}
        language = self._qwen_language(task.language)
        if language:
            asr_options["language"] = language

        payload = {
            "model": model_name or "qwen3-asr-flash",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {"data": audio_data},
                        }
                    ],
                }
            ],
            "stream": False,
            "asr_options": asr_options,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        url = api_base.rstrip("/")
        if not url.endswith("/chat/completions"):
            url += "/chat/completions"
        async with httpx.AsyncClient(timeout=240) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        transcript = self._extract_text(data)
        if not transcript:
            raise RuntimeError("Qwen-ASR 没有返回转写文本")
        return TranscriptionResult(
            transcript=transcript,
            summary="已完成真实 ASR 转写，可继续用于脚本结构、钩子和剪辑节奏分析。",
            hook_analysis="请在参考解析中结合前三句、停顿和画面变化进一步提炼开头钩子。",
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

    def _is_qwen_asr(self, provider: str, model_name: str) -> bool:
        normalized_provider = (provider or "").lower()
        normalized_model = (model_name or "").lower()
        return normalized_provider in QWEN_ASR_PROVIDERS and "asr" in normalized_model

    def _qwen_audio_input(self, material: Material) -> str:
        path = self._local_material_path(material.file_path)
        if path:
            return self._qwen_local_audio_input(path)
        if material.source_url and self._looks_like_media_url(material.source_url):
            return material.source_url
        raise RuntimeError("素材没有可用于 ASR 的本地音频/视频文件或公网媒体 URL")

    def _local_material_path(self, file_path: str | None) -> Path | None:
        if not file_path:
            return None
        original = Path(file_path)
        candidates = [original]
        if not original.is_absolute():
            candidates.extend([Path.cwd() / original, Path("/app") / original])
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _qwen_local_audio_input(self, path: Path) -> str:
        audio_path = self._extract_audio_for_asr(path) if path.suffix.lower() in QWEN_ASR_VIDEO_EXTENSIONS else path
        if audio_path.stat().st_size > QWEN_ASR_BASE64_MAX_BYTES:
            raise RuntimeError("Qwen-ASR 本地 Base64 输入不能超过 7.5MB，请先把音频上传到可访问的 OSS/公网 URL。")
        mime_type = mimetypes.guess_type(audio_path.name)[0] or "audio/mpeg"
        encoded = base64.b64encode(audio_path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    def _extract_audio_for_asr(self, video_path: Path) -> Path:
        audio_path = video_path.with_suffix(".asr.wav")
        if audio_path.exists() and audio_path.stat().st_size > 0:
            return audio_path
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-acodec",
            "pcm_s16le",
            str(audio_path),
        ]
        try:
            subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        except FileNotFoundError as exc:
            raise RuntimeError("服务器未安装 ffmpeg，无法从视频中提取 ASR 音频。") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or "").strip().splitlines()[-1:] or ["未知错误"]
            raise RuntimeError(f"视频音频提取失败：{detail[0]}") from exc
        if not audio_path.exists() or audio_path.stat().st_size == 0:
            raise RuntimeError("视频音频提取失败：没有生成可用音频文件")
        return audio_path

    def _looks_like_media_url(self, source_url: str) -> bool:
        suffix = Path(source_url.split("?", 1)[0]).suffix.lower()
        if suffix in QWEN_ASR_MEDIA_EXTENSIONS:
            return True
        lowered = source_url.lower()
        return "finder.video.qq.com" in lowered or any(marker in lowered for marker in ("download", "media", "video", "play"))

    def _qwen_language(self, language: str) -> str:
        normalized = (language or "").lower()
        if normalized.startswith("zh"):
            return "zh"
        if normalized.startswith("en"):
            return "en"
        return ""

    def _extract_text(self, data: Any) -> str:
        if isinstance(data, str):
            return data
        if isinstance(data, list):
            parts = []
            for item in data:
                text = self._extract_text(item)
                if text:
                    parts.append(text)
            return "\n".join(parts)
        if not isinstance(data, dict):
            return ""
        choices = data.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                if isinstance(choice, dict):
                    message = choice.get("message")
                    if isinstance(message, dict):
                        content = message.get("content")
                        if isinstance(content, str):
                            return content
                        text = self._extract_text(content)
                        if text:
                            return text
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
