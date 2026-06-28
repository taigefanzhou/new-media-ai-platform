# Integrations

The MVP is designed to run without paid services. Every generation step has a `mock` mode and a real-service mode.

This file describes how each API/model integration should be connected: providers, environment variables, request payloads, and expected responses.

For the current online runtime state, read `docs/system-status-handoff.md` first. Whenever an integration is added, removed, switched from mock to real API, or changed in production, update both files:

- `docs/integrations.md`: how the integration works.
- `docs/system-status-handoff.md`: whether it is actually configured, verified, and live.

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

## Subtitle Engine

The platform has a built-in subtitle post-processing engine in `backend/app/services/subtitles.py`.

It is not a third-party SaaS integration. It uses the generated script text, task duration/profile metadata, ASS/SRT files, and FFmpeg to create a captioned MP4:

```text
local video -> script voiceover timing -> captions.srt -> captions.ass -> FFmpeg burn-in -> captioned-video.mp4
```

Current task fields:

```text
subtitle_enabled
subtitle_style
subtitle_status
subtitle_srt_path
subtitle_ass_path
captioned_output_path
```

Supported styles:

```text
auto
business
viral
digital_human
tutorial
minimal
```

Runtime behavior:

- New video tasks enable subtitles by default.
- `auto` chooses a style from production mode and script duration.
- The creation page chooses a runnable generation route from `/api/integrations/status`: real digital human first, then real video generation, otherwise local `dynamic_explainer` preview.
- Preview, storage summary, and publish validation prefer `captioned_output_path` when it exists.
- The engine requires a local video file and FFmpeg. It skips `mock://` outputs and remote URLs instead of pretending success.
- Current timing is automatically distributed from the script voiceover text and final video duration.
- When real ASR or word-level timestamps are available, the same ASS/SRT stage can be fed with ASR-derived cue timing for more accurate karaoke/highlight captions.

## Volcengine Jimeng Digital Human

The system has an adapter entry for Volcengine Jimeng digital human:

```text
provider=volcengine-jimeng-digital-human
purpose=digital_human
api_base=https://visual.volcengineapi.com
credential platform=volcengine
credential purpose=digital_human
service=cv
region=cn-north-1
submit action=CVSync2AsyncSubmitTask
result action=CVSync2AsyncGetResult
version=2022-08-31
app_id=101606596
req_key=pippit_iv2v_v20_cvtob_with_vinput
```

Credential mapping:

```text
PlatformCredential.client_id     -> AccessKeyID
PlatformCredential.client_secret -> SecretAccessKey
```

This is not marked as the default production adapter yet. The local adapter can sign and submit Volcengine OpenAPI requests with AK/SK, and the same signing chain has been validated against IAM. After Volcengine Xiaoyunque service activation, a real sample was generated:

```text
task_id=1fd5262a72c711f1a494043f72b46be0
sample=https://media.tech-ark.com/asset-uploads/volcengine-jimeng-sample-20260628.mp4
```

This route uses a public portrait image URL plus a public reference video URL. It is a reference-video generation route, not strict audio-driven lip sync.

See `docs/volcengine-jimeng-digital-human.md`.

## Remotion Professional Renderer

The project includes a Remotion-based renderer in `services/remotion-renderer`.

Purpose:

```text
base video -> Remotion professional template -> packaged MP4 -> subtitle engine / review / storage
```

Configuration:

```bash
COMPOSITION_PROVIDER="remotion"
REMOTION_RENDER_API_BASE="http://remotion-renderer:3100"
REMOTION_RENDER_TEMPLATE="business_talking"
```

Service endpoints:

```text
GET  /health
POST /render
```

`POST /render` accepts:

```json
{
  "source_video_path": "/app/data/final/.../base.mp4",
  "output_path": "/app/data/composition/remotion/task-1/professional-video.mp4",
  "width": 1080,
  "height": 1920,
  "duration_seconds": 60,
  "title": "视频标题",
  "hook": "开头钩子",
  "voiceover": "口播稿",
  "brand_name": "TECHARK",
  "scenes": []
}
```

Current template:

- `business_talking`
- Base video layer.
- Animated background.
- Top title and brand bar.
- Scene card / selling-point card.
- Bottom caption zone.
- Progress bar.

Current online deployment:

- Production is running `COMPOSITION_PROVIDER=remotion`.
- Renderer container: `server-remotion-renderer-1`.
- Renderer image: `new-media-remotion-renderer:20260628-professional`.
- `/api/integrations/status` should show `composition.provider=remotion` and `composition.real_api=true`.
- Verified online render output: `/opt/new-media-ai-platform/backend/data/remotion-test/output.mp4`.

Production deployment note:

- Do not build this image directly on the production host unless there is an explicit maintenance window.
- Production currently blocks Docker build through `/opt/factory-manager/shared/state/.production-no-docker-build`.
- Build the renderer image in CI/build machine, push it, then deploy with `docker compose pull && docker compose up -d --no-build`.
- The temporary tar-based path used for this release is: build linux/amd64 image outside production, upload tar, `docker load`, then `docker compose up -d --no-build`.
- Runtime installation of Chromium works for development but is too slow and heavy for production startup.

## Link Resolver / Reference Material Collection

The reference-material import flow supports pasting public short-video links into the app.

The backend first tries direct media URLs and public page metadata. If the page does not expose a downloadable media URL, it calls active platform credentials whose `purpose` is `link_resolver`.

Generic resolver configuration:

```text
platform: wechat_channels / douyin / xiaohongshu / kuaishou / manual
purpose: link_resolver
api_base: https://your-resolver.example.com/api/fetch_video_profile
notes:
  method=post
  timeout=8
```

Generic request payload:

```json
{
  "url": "https://weixin.qq.com/sph/...",
  "source_url": "https://weixin.qq.com/sph/...",
  "share_url": "https://weixin.qq.com/sph/...",
  "platform": "wechat_channels"
}
```

Generic resolver responses may return common fields such as:

```json
{
  "data": {
    "feedInfo": {
      "description": "视频描述",
      "h264VideoInfo": {"videoUrl": "https://finder.video.qq.com/.../stodownload?..."},
      "likeCountFmt": "123",
      "commentCountFmt": "45"
    },
    "authorInfo": {"nickname": "作者"}
  }
}
```

Just One WeChat Channels configuration:

```text
platform: wechat_channels
purpose: link_resolver
api_base: http://47.117.133.51:30015
access_token: <Just One token>
notes:
  provider=justone
  timeout=12
```

The backend calls:

```text
GET {api_base}/api/weixin-channels/get-video-basic-info/v1
GET {api_base}/api/weixin-channels/get-video-download-url/v1
```

The app stores unresolved links as reference-only materials instead of pretending that the video file was downloaded. The link resolver test endpoint returns `diagnostics` so operators can tell whether a failure is caused by an unreachable resolver, missing token, timeout, or a resolver response without a video URL.

## Topic/Trending Search

The product has two video acquisition entrances:

- Link reference parsing for concrete Douyin/WeChat Channels URLs.
- Topic search collection for keyword-driven discovery.

Use platform-specific credentials when possible. Douyin can use TikHub or a self-hosted crawler adapter. WeChat Channels topic search should only be enabled after a dedicated collector is configured; otherwise use link parsing for specific video URLs.

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
  "limit": 20,
  "count": 20,
  "cursor": 0,
  "sort_type": "0",
  "sort_by": "engagement",
  "min_like_count": 1000,
  "min_comment_count": 50
}
```

Platform credentials can override the generic endpoint. Add a platform credential with:

```text
purpose=trending
api_base=https://api.tikhub.io
access_token=<TikHub API Key>
notes:
provider=tikhub
method=post
timeout=20
path=/api/v1/douyin/search/fetch_video_search_v2
```

For TikHub Douyin search, the backend sends `keyword`, `cursor`, `sort_type`, `publish_time`, `filter_duration`, `content_type`, `search_id`, and `backtrace`, matching the documented video search V2 shape. Replace `path` for WeChat Channels or other providers according to the provider console.

The response may be a list or an object containing `items`, `videos`, `data`, `results`, `list`, `aweme_list`, `awemes`, `feeds`, or `records`.

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

The extractor also recognizes common nested Douyin/TikTok fields such as `statistics.digg_count`, `statistics.comment_count`, `statistics.share_count`, and `share_info.share_url`.

This module is for compliant topic research. Save collected entries as reference materials for analysis, not as proof of download rights. Do not copy footage, captions, or scripts from unlicensed videos.

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
