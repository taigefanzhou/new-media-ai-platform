# Integrations

The MVP is designed to run without paid services. Every generation step has a `mock` mode and a real-service mode.

## Status

Open the admin console and check the integration strip:

```text
http://localhost:8000/
```

Or call:

```bash
curl http://localhost:8000/api/integrations/status
```

## Script Model

Use any OpenAI-compatible chat completions provider:

```bash
LLM_PROVIDER="openai-compatible"
LLM_API_BASE="https://api.openai.com/v1"
LLM_API_KEY="..."
LLM_MODEL="gpt-4.1-mini"
```

The backend calls:

```text
POST {LLM_API_BASE}/chat/completions
```

## TTS

Default:

```bash
TTS_PROVIDER="mock"
```

Generic real service:

```bash
TTS_PROVIDER="cosyvoice"
TTS_API_BASE="http://localhost:9880"
TTS_API_KEY=""
TTS_VOICE="default"
```

The backend calls:

```text
POST {TTS_API_BASE}/synthesize
```

Payload:

```json
{
  "text": "口播文本",
  "voice": "default",
  "format": "wav"
}
```

Expected response: binary WAV bytes.

## Digital Human

Default:

```bash
DIGITAL_HUMAN_PROVIDER="mock"
```

Generic real service:

```bash
DIGITAL_HUMAN_PROVIDER="sadtalker"
DIGITAL_HUMAN_API_BASE="http://localhost:7860"
DIGITAL_HUMAN_API_KEY=""
```

The backend calls:

```text
POST {DIGITAL_HUMAN_API_BASE}/generate
```

Payload:

```json
{
  "provider": "sadtalker",
  "portrait_path": "/path/to/portrait.png",
  "audio_path": "/path/to/voiceover.wav",
  "format": "mp4"
}
```

Expected response can include `url`, `video_url`, `output_url`, `path`, or `output_path`.

## Video Generation

Mock:

```bash
VIDEO_GENERATION_PROVIDER="mock"
```

Seedance-style provider:

```bash
VIDEO_GENERATION_PROVIDER="seedance"
SEEDANCE_API_BASE="https://provider.example.com/v1"
SEEDANCE_API_KEY="..."
SEEDANCE_MODEL="seedance"
```

The backend calls:

```text
POST {SEEDANCE_API_BASE}/videos/generations
```

Payload:

```json
{
  "model": "seedance",
  "prompt": "Vertical 9:16 corporate short video...",
  "aspect_ratio": "9:16",
  "duration": 5
}
```

ComfyUI mode:

```bash
VIDEO_GENERATION_PROVIDER="comfyui"
COMFYUI_API_BASE="http://localhost:8188"
```

The backend calls:

```text
POST {COMFYUI_API_BASE}/prompt
```

## Composition

Mock:

```bash
COMPOSITION_PROVIDER="mock"
```

FFmpeg concat mode:

```bash
COMPOSITION_PROVIDER="ffmpeg"
FFMPEG_BINARY="ffmpeg"
```

This mode concatenates local MP4 paths returned by upstream services. Remote URLs should be downloaded by the provider adapter before enabling production use.

## Trending Search

Mock mode:

```bash
TRENDING_SEARCH_PROVIDER="mock"
```

Generic HTTP JSON provider:

```bash
TRENDING_SEARCH_PROVIDER="http-json"
TRENDING_SEARCH_API_BASE="https://provider.example.com/api"
TRENDING_SEARCH_API_KEY="..."
```

The backend calls:

```text
POST {TRENDING_SEARCH_API_BASE}/trending/search
```

Payload:

```json
{
  "platform": "douyin",
  "keyword": "数字人获客",
  "category": "企业服务",
  "limit": 20
}
```

The response may be a list or an object containing `items`, `videos`, `data`, `results`, or `list`.

Each item can use common field names:

```json
{
  "title": "视频标题",
  "url": "https://...",
  "author": "作者",
  "views": 100000,
  "likes": 8000,
  "comments": 300,
  "shares": 500,
  "duration": 35,
  "hook": "开头爆点",
  "summary": "结构分析",
  "tags": ["数字人", "获客"]
}
```

This module is for compliant topic research. Do not copy footage, captions, or scripts from unlicensed videos.

## ASR / Reference Video Transcription

Mock mode:

```bash
ASR_PROVIDER="mock"
```

Volcengine/Doubao ASR adapter mode:

```bash
ASR_PROVIDER="volcengine"
ASR_API_BASE="https://your-asr-adapter.example.com"
ASR_API_KEY="..."
ASR_MODEL="volcengine-asr"
```

The backend calls:

```text
POST {ASR_API_BASE}/asr/transcriptions
```

Payload:

```json
{
  "model": "volcengine-asr",
  "language": "zh-CN",
  "file_path": "./data/storage/materials/.../source.mp4",
  "source_url": null,
  "material_name": "参考视频"
}
```

Expected response can include `text`, `transcript`, `result`, `content`, `segments`, or `utterances`.

The Volcengine document the user shared is useful for this module: it turns reference audio/video speech into text, which can then be analyzed and rewritten into original company scripts.
