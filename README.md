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

## Docker Start

```bash
cd infra
cp ../backend/.env.example ../backend/.env
docker compose up --build
```

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
2. Create a topic.
3. Generate a script.
4. Create a digital human.
5. Create a video task.
6. Run the video task.
7. Approve the result.
8. Prepare a publish record.

The current media generation implementation returns mock URLs so the business flow can be tested before connecting paid or GPU services.

## Verification

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/dashboard
```
