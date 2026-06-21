# New Media AI Video Platform MVP

This is a practical MVP scaffold for a company short-video production platform.

It covers:

- Material library
- Topic library
- AI script generation
- Digital human registry
- Video generation tasks
- Review/approval
- Publish preparation records
- Extension points for Dify, n8n, ComfyUI, Seedance, CosyVoice, MuseTalk, SadTalker, LivePortrait, and FFmpeg

## Quick Start

```bash
cd backend
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open:

- Admin console: `http://localhost:8000/`
- API health: `http://localhost:8000/api/health`
- API docs: `http://localhost:8000/docs`

The admin console can already create topics, generate scripts, create digital humans, create video tasks, run mock generation, and inspect task status.
It also supports uploading local image/video assets, including portrait photos for digital human creation.

Default admin login:

```text
username: admin
password: admin123456
```

Change these in `backend/.env` before production:

```bash
ADMIN_USERNAME="admin"
ADMIN_PASSWORD="replace-with-a-strong-password"
```

## Script Model Setup

By default, the platform uses a stub script generator so the product flow works without paid services.

To use a real OpenAI-compatible model provider, set these values in `backend/.env`:

```bash
LLM_PROVIDER="openai-compatible"
LLM_API_BASE="https://api.openai.com/v1"
LLM_API_KEY="your_api_key"
LLM_MODEL="gpt-4.1-mini"
```

For DeepSeek, Tongyi, Doubao, or a self-hosted vLLM server, keep `LLM_PROVIDER="openai-compatible"` and replace `LLM_API_BASE`, `LLM_API_KEY`, and `LLM_MODEL` with that provider's values.

You can also maintain model entries in the admin console under system settings. The active `script` model takes priority when generating scripts.
For this project, the recommended production order is Volcengine Ark/Doubao Seed first, then Alibaba Cloud Bailian/Qwen as backup.
See `docs/model-selection.md` for the current model recommendation table.

## Trending Video Collection

The admin console includes a trending-video collection area:

- Create platform + keyword collection tasks.
- Run mock collection to populate structured references.
- Manually save reference video links.
- Store hook, summary, tags, and metrics as inspiration.
- Connect a real HTTP JSON data source with `TRENDING_SEARCH_PROVIDER="http-json"`.
- Maintain platform API credentials in system settings and activate one credential per platform/use case.

## Reference Video Analysis

The admin console includes a reference analysis module:

- Upload reference audio/video as a material.
- Create an ASR transcription task with the material ID.
- Run transcription to get transcript, summary, and hook analysis.
- Use the transcript as input for original topic and script generation.
- Generate a topic or an original script directly from the transcription result.
- Create a video task directly from a generated script.
- Run, approve, and prepare publishing records from video tasks.
- Maintain platform accounts for Douyin, WeChat Channels, Xiaohongshu, and Kuaishou.
- Mark a default platform account for each publishing platform.
- Edit publish titles, hashtags, captions, account selection, schedules, and publishing status.

Volcengine/Doubao ASR can be connected through:

```bash
ASR_PROVIDER="volcengine"
ASR_API_BASE="https://your-asr-adapter.example.com"
ASR_API_KEY="..."
ASR_MODEL="volcengine-asr"
```

The app calls `{ASR_API_BASE}/asr/transcriptions`. For production, wrap the official Volcengine ASR API behind this adapter shape.

This module is designed for compliant ideation. Reference videos should be used for topic and structure analysis only, not for copying footage, captions, or scripts.

For WeChat Channels link parsing, see `docs/wechat-channels-link-resolver.md`.

## Docker Start

```bash
cd infra
cp ../backend/.env.example ../backend/.env
docker compose up --build
```

Production deployment on your own OpenCloudOS server is documented in `docs/deploy-own-server.md`.

Optional workflow service:

```bash
docker compose --profile workflow up --build
```

Optional GPU ComfyUI service:

```bash
docker compose --profile gpu up --build
```

## MVP Flow

1. Create a material.
   - Or upload a file through `/api/materials/upload`.
2. Create a topic.
3. Generate a script.
4. Create a digital human and optionally bind a portrait material.
5. Create a video task.
6. Run the video task.
7. Approve the result.
8. Prepare a publish record.
9. Review the publish workbench, adjust title/caption/schedule/account, and mark the record as published, failed, or canceled.

The current media generation implementation returns mock URLs so the business flow can be tested before connecting paid or GPU services.

## Verification

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/dashboard
curl http://localhost:8000/api/integrations/status
```

More integration details are in `docs/integrations.md`.
