from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
import subprocess
from typing import Iterable
from uuid import uuid4

from app.core.config import get_settings
from app.core.storage import get_storage_root
from app.models.entities import Script, VideoTask
from app.services.export_profiles import resolve_export_profile


@dataclass
class SubtitleCue:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class SubtitleTemplate:
    key: str
    label: str
    font_name: str
    font_size: int
    margin_v: int
    primary_color: str
    highlight_color: str
    outline_color: str
    back_color: str
    outline: int = 4
    shadow: int = 2
    bold: int = 1
    max_chars_per_line: int = 15
    max_lines: int = 2


SUBTITLE_TEMPLATES: dict[str, SubtitleTemplate] = {
    "business": SubtitleTemplate(
        key="business",
        label="商务清晰",
        font_name="Noto Sans CJK SC",
        font_size=52,
        margin_v=150,
        primary_color="&H00FFFFFF",
        highlight_color="&H0000D7FF",
        outline_color="&H00101A2B",
        back_color="&H8A101A2B",
        max_chars_per_line=16,
    ),
    "viral": SubtitleTemplate(
        key="viral",
        label="爆款大字",
        font_name="Noto Sans CJK SC",
        font_size=64,
        margin_v=210,
        primary_color="&H00FFFFFF",
        highlight_color="&H0000E8FF",
        outline_color="&H00000000",
        back_color="&H7A000000",
        outline=6,
        shadow=3,
        max_chars_per_line=12,
    ),
    "digital_human": SubtitleTemplate(
        key="digital_human",
        label="参考口播字幕",
        font_name="Noto Serif CJK SC",
        font_size=64,
        margin_v=225,
        primary_color="&H00FFFFFF",
        highlight_color="&H0000D7FF",
        outline_color="&H00000000",
        back_color="&H80000000",
        outline=4,
        shadow=2,
        max_chars_per_line=15,
        max_lines=1,
    ),
    "tutorial": SubtitleTemplate(
        key="tutorial",
        label="教程说明",
        font_name="Noto Sans CJK SC",
        font_size=48,
        margin_v=135,
        primary_color="&H00F8FAFC",
        highlight_color="&H004ADE80",
        outline_color="&H00111827",
        back_color="&H8A111827",
        max_chars_per_line=17,
    ),
    "minimal": SubtitleTemplate(
        key="minimal",
        label="极简底栏",
        font_name="Noto Sans CJK SC",
        font_size=44,
        margin_v=120,
        primary_color="&H00FFFFFF",
        highlight_color="&H00FFFFFF",
        outline_color="&H00111111",
        back_color="&H5A111111",
        outline=3,
        shadow=1,
        bold=0,
        max_chars_per_line=18,
    ),
}


class SubtitleEngine:
    def __init__(self) -> None:
        self.settings = get_settings()

    def render_for_task(self, task: VideoTask, script: Script) -> VideoTask:
        if not task.subtitle_enabled:
            task.subtitle_status = "disabled"
            return task
        input_path = self._local_video_path(task.output_path)
        if input_path is None:
            task.subtitle_status = "skipped"
            note = "字幕引擎未执行：当前成片不是服务器本地文件，无法用 FFmpeg 烧录字幕。"
            task.audit_notes = f"{task.audit_notes}\n{note}".strip()
            return task
        if not self._ffmpeg_available():
            task.subtitle_status = "failed"
            task.error_message = task.error_message or "服务器未安装 FFmpeg，无法自动生成字幕成片。"
            return task

        template = self._resolve_template(task, script)
        duration = self._probe_duration(input_path) or float(script.duration_seconds or 0) or 30.0
        cues = self._build_cues(script.voiceover, duration, template)
        if not cues:
            task.subtitle_status = "skipped"
            return task

        output_dir = get_storage_root() / "subtitles" / f"task-{task.id or uuid4().hex}"
        output_dir.mkdir(parents=True, exist_ok=True)
        srt_path = output_dir / "captions.srt"
        ass_path = output_dir / "captions.ass"
        manifest_path = output_dir / "captions.json"
        captioned_path = output_dir / "captioned-video.mp4"

        srt_path.write_text(self._to_srt(cues), encoding="utf-8")
        ass_path.write_text(self._to_ass(cues, template, task.export_width, task.export_height), encoding="utf-8")
        manifest_path.write_text(
            json.dumps(
                {
                    "task_id": task.id,
                    "template": template.key,
                    "template_label": template.label,
                    "duration_seconds": duration,
                    "cue_count": len(cues),
                    "source": "script_voiceover",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        self._burn_ass(input_path, ass_path, captioned_path)

        task.subtitle_style = template.key
        task.subtitle_status = "completed"
        task.subtitle_srt_path = str(srt_path)
        task.subtitle_ass_path = str(ass_path)
        task.captioned_output_path = str(captioned_path)
        task.audit_notes = (
            f"{task.audit_notes}\n字幕引擎：已自动生成 {template.label} 字幕，"
            f"{len(cues)} 条字幕，成片已切换为带字幕版本。"
        ).strip()
        return task

    def _resolve_template(self, task: VideoTask, script: Script) -> SubtitleTemplate:
        requested = (task.subtitle_style or "auto").strip()
        if requested and requested != "auto" and requested in SUBTITLE_TEMPLATES:
            return SUBTITLE_TEMPLATES[requested]
        if task.production_mode in {"digital_human", "talking_head_template"}:
            return SUBTITLE_TEMPLATES["digital_human"]
        if task.production_mode == "dynamic_explainer":
            return SUBTITLE_TEMPLATES["tutorial"]
        if script.duration_seconds <= 75:
            return SUBTITLE_TEMPLATES["viral"]
        return SUBTITLE_TEMPLATES["business"]

    def _build_cues(self, text: str, duration: float, template: SubtitleTemplate) -> list[SubtitleCue]:
        chunks = self._split_text(text, template.max_chars_per_line * template.max_lines)
        if template.key == "digital_human":
            chunks = self._polish_talking_head_chunks(chunks, template.max_chars_per_line)
        if not chunks:
            return []
        weights = [max(4, len(re.sub(r"\s+", "", chunk))) for chunk in chunks]
        total_weight = sum(weights)
        current = 0.35
        usable_duration = max(1.0, duration - 0.7)
        cues: list[SubtitleCue] = []
        for chunk, weight in zip(chunks, weights):
            cue_duration = max(1.15, usable_duration * weight / total_weight)
            end = min(duration, current + cue_duration)
            if end - current < 0.7:
                end = min(duration, current + 0.7)
            cues.append(SubtitleCue(start=current, end=end, text=chunk))
            current = end
            if current >= duration - 0.2:
                break
        if cues:
            cues[-1].end = min(duration, max(cues[-1].end, duration - 0.15))
        return cues

    def _split_text(self, text: str, max_chars: int) -> list[str]:
        cleaned = re.sub(r"\s+", " ", (text or "").strip())
        if not cleaned:
            return []
        sentences = [item.strip() for item in re.split(r"(?<=[。！？!?；;])", cleaned) if item.strip()]
        if not sentences:
            sentences = [cleaned]
        chunks: list[str] = []
        current = ""
        for sentence in sentences:
            pieces = self._chunk_long_sentence(sentence, max_chars)
            for piece in pieces:
                candidate = f"{current}{piece}" if current else piece
                if len(candidate) <= max_chars:
                    current = candidate
                else:
                    if current:
                        chunks.append(current)
                    current = piece
        if current:
            chunks.append(current)
        return chunks

    def _chunk_long_sentence(self, sentence: str, max_chars: int) -> list[str]:
        if len(sentence) <= max_chars:
            return [sentence]
        parts = [item for item in re.split(r"(?<=[，,、：:])", sentence) if item]
        chunks: list[str] = []
        current = ""
        for part in parts:
            candidate = f"{current}{part}" if current else part
            if len(candidate) <= max_chars:
                current = candidate
                continue
            if current:
                chunks.append(current)
            if len(part) <= max_chars:
                current = part
            else:
                chunks.extend(part[i : i + max_chars] for i in range(0, len(part), max_chars))
                current = ""
        if current:
            chunks.append(current)
        return chunks

    def _polish_talking_head_chunks(self, chunks: list[str], max_chars: int) -> list[str]:
        polished: list[str] = []
        for chunk in chunks:
            text = re.sub(r"[，,、：:；;。！？!?]+$", "", chunk.strip())
            if not text:
                continue
            if polished and len(text) <= 4 and len(polished[-1] + text) <= max_chars + 2:
                polished[-1] = f"{polished[-1]}{text}"
            else:
                polished.append(text)
        return polished

    def _to_srt(self, cues: Iterable[SubtitleCue]) -> str:
        blocks = []
        for index, cue in enumerate(cues, start=1):
            blocks.append(
                f"{index}\n{self._srt_time(cue.start)} --> {self._srt_time(cue.end)}\n{cue.text}\n"
            )
        return "\n".join(blocks)

    def _to_ass(self, cues: Iterable[SubtitleCue], template: SubtitleTemplate, width: int, height: int) -> str:
        profile = resolve_export_profile(None)
        play_res_x = int(width or profile.width)
        play_res_y = int(height or profile.height)
        lines = [
            "[Script Info]",
            "ScriptType: v4.00+",
            "WrapStyle: 2",
            "ScaledBorderAndShadow: yes",
            f"PlayResX: {play_res_x}",
            f"PlayResY: {play_res_y}",
            "",
            "[V4+ Styles]",
            (
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
                "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
                "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
            ),
            (
                f"Style: Default,{template.font_name},{template.font_size},{template.primary_color},{template.highlight_color},"
                f"{template.outline_color},{template.back_color},{template.bold},0,0,0,100,100,0,0,1,"
                f"{template.outline},{template.shadow},2,64,64,{template.margin_v},1"
            ),
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
        for cue in cues:
            text = self._ass_wrap(self._highlight_keywords(cue.text, template), template)
            lines.append(
                f"Dialogue: 0,{self._ass_time(cue.start)},{self._ass_time(cue.end)},Default,,0,0,0,,{text}"
            )
        return "\n".join(lines) + "\n"

    def _highlight_keywords(self, text: str, template: SubtitleTemplate) -> str:
        escaped = self._escape_ass_text(text)
        if template.key == "minimal":
            return escaped
        patterns = [
            r"\d+(?:\.\d+)?%?",
            r"旺季",
            r"利润",
            r"入住",
            r"控房",
            r"能耗",
            r"智能(?:房态|门锁|化)?",
            r"动态调价",
            r"自助入住",
            r"保洁",
            r"清单",
            r"省(?:钱|电|成本)?",
            r"酒店",
            r"客户",
            r"系统",
            r"方案",
            r"数字人",
            r"获客",
            r"成本",
        ]
        highlighted = escaped
        resets = r"{\c" + template.primary_color + "}"
        prefix = r"{\c" + template.highlight_color + "}"
        used = 0
        for pattern in patterns:
            def repl(match: re.Match[str]) -> str:
                nonlocal used
                if used >= 4:
                    return match.group(0)
                used += 1
                return f"{prefix}{match.group(0)}{resets}"

            highlighted = re.sub(pattern, repl, highlighted, count=1)
        return highlighted

    def _ass_wrap(self, text: str, template: SubtitleTemplate) -> str:
        plain = re.sub(r"\{\\[^}]+}", "", text)
        if len(plain) <= template.max_chars_per_line:
            return text
        break_at = self._line_break_index(plain, template.max_chars_per_line)
        if break_at <= 0:
            return text
        return self._insert_ass_break(text, break_at)

    def _line_break_index(self, text: str, limit: int) -> int:
        if len(text) <= limit:
            return -1
        candidates = [idx for idx, char in enumerate(text[: limit + 3]) if char in "，,、：: "]
        return (candidates[-1] + 1) if candidates else limit

    def _insert_ass_break(self, text: str, plain_index: int) -> str:
        plain_seen = 0
        out = []
        in_tag = False
        inserted = False
        for char in text:
            if char == "{" and not in_tag:
                in_tag = True
            if not inserted and not in_tag and plain_seen >= plain_index:
                out.append(r"\N")
                inserted = True
            out.append(char)
            if char == "}" and in_tag:
                in_tag = False
                continue
            if not in_tag:
                plain_seen += 1
        return "".join(out)

    def _escape_ass_text(self, text: str) -> str:
        return (text or "").replace("{", "｛").replace("}", "｝").replace("\n", " ")

    def _burn_ass(self, input_path: Path, ass_path: Path, output_path: Path) -> None:
        filter_path = str(ass_path.resolve()).replace("\\", "\\\\").replace(":", "\\:")
        fonts_dir = self._subtitle_fonts_dir()
        filter_value = f"ass={filter_path}"
        if fonts_dir:
            escaped_fonts_dir = str(fonts_dir.resolve()).replace("\\", "\\\\").replace(":", "\\:")
            filter_value = f"{filter_value}:fontsdir={escaped_fonts_dir}"
        command = [
            self.settings.ffmpeg_binary,
            "-y",
            "-i",
            str(input_path),
            "-vf",
            filter_value,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            str(output_path),
        ]
        try:
            subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or "").strip().splitlines()[-1:] or ["未知错误"]
            raise RuntimeError(f"字幕烧录失败：{detail[0]}") from exc

    def _subtitle_fonts_dir(self) -> Path | None:
        storage_root = get_storage_root()
        candidates = [storage_root / "fonts", storage_root.parent / "fonts"]
        for candidate in candidates:
            if candidate.exists() and any(candidate.glob("NotoSansCJK*.ttc")):
                return candidate
        return None

    def _probe_duration(self, input_path: Path) -> float | None:
        command = [
            self.settings.ffmpeg_binary.replace("ffmpeg", "ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(input_path),
        ]
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            return float((result.stdout or "").strip())
        except Exception:
            return None

    def _ffmpeg_available(self) -> bool:
        try:
            subprocess.run([self.settings.ffmpeg_binary, "-version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            return False

    def _local_video_path(self, output_path: str | None) -> Path | None:
        if not output_path or output_path.startswith(("http://", "https://", "mock://")):
            return None
        original = Path(output_path)
        candidates = [original]
        if not original.is_absolute():
            candidates.extend([Path.cwd() / original, Path("/app") / original])
        workspace_backend = "/Users/Admin/Documents/Codex/2026-06-19/r/outputs/new-media-ai-platform/backend"
        if output_path.startswith(workspace_backend):
            candidates.append(Path(output_path.replace(workspace_backend, "/opt/new-media-ai-platform/backend")))
            candidates.append(Path(output_path.replace(workspace_backend, "/app")))
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    def _srt_time(self, seconds: float) -> str:
        millis = int(round(seconds * 1000))
        hours, remainder = divmod(millis, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        secs, ms = divmod(remainder, 1000)
        return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"

    def _ass_time(self, seconds: float) -> str:
        centis = int(round(seconds * 100))
        hours, remainder = divmod(centis, 360_000)
        minutes, remainder = divmod(remainder, 6_000)
        secs, cs = divmod(remainder, 100)
        return f"{hours}:{minutes:02}:{secs:02}.{cs:02}"
