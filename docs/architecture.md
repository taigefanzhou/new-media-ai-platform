# Architecture

## Fastest Practical Stack

```text
React/FastAPI business console
  |
  |-- Dify or direct LLM API: topic analysis, scripts, titles, storyboards, compliance checks
  |-- CosyVoice/Fish Speech/EmotiVoice: TTS and authorized voice cloning
  |-- SadTalker/MuseTalk/LivePortrait: digital human talking video
  |-- Seedance API or ComfyUI + Wan2.1: video shots and background scenes
  |-- FFmpeg: composition, subtitles, logo, BGM, export presets
  |-- n8n: optional workflow automation and platform notification hooks
```

## Service Boundaries

The backend intentionally keeps AI vendors behind adapters:

- `ScriptGenerator`
- `MediaGenerationClient.synthesize_voice`
- `MediaGenerationClient.generate_talking_avatar`
- `MediaGenerationClient.generate_seedance_clips`
- `MediaGenerationClient.compose_final_video`

Replace these implementations when a real service is ready.

## Recommended Production Order

1. Connect a strong LLM for scripts first.
2. Connect CosyVoice for Mandarin TTS.
3. Connect SadTalker for one-photo MVP digital human.
4. Add MuseTalk for higher quality lip sync.
5. Connect Seedance API for final video shots.
6. Add ComfyUI/Wan2.1 as open-source fallback.
7. Add n8n only for cross-platform notification and publishing workflows.

## Compliance Notes

- Reference videos are for topic structure only.
- Do not re-upload or lightly modify unlicensed videos.
- Portrait uploads require explicit authorization.
- Generated AI content should follow platform AI labeling rules.
- Keep manual review before publishing.
