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
