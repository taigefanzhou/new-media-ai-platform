# Model Selection

## Script Generation

Fastest:

- Hosted OpenAI-compatible API
- Dify workflow in front of Qwen, DeepSeek, OpenAI, Doubao, or Tongyi

Open-source local:

- Qwen3 Instruct for Chinese scripts and storyboards
- vLLM for serving when GPU is available

## TTS

Primary:

- CosyVoice: strong Mandarin and multilingual TTS, voice cloning path

Alternatives:

- Fish Speech
- EmotiVoice for Chinese/English emotion-controlled TTS

## Digital Human

MVP:

- SadTalker: one portrait plus audio to talking head video

Higher quality:

- MuseTalk: lip sync for existing person/digital-human video
- LivePortrait: portrait animation and expression control

Avoid:

- Wav2Lip for commercial use unless separately licensed.

## Video Generation

Primary if API access exists:

- Seedance API

Open-source fallback:

- Wan2.1, especially T2V-1.3B for easier local deployment
- LTX-Video for ComfyUI-oriented workflows
- HunyuanVideo for high-quality but heavier inference
- CogVideoX for mature open video generation
