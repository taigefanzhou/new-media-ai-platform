# Model Selection Guide

Current recommendation for this platform:

1. Use Volcengine Ark first for script generation, compliance rewriting, and Seedance video generation.
2. Use Alibaba Cloud Bailian Qwen as the second choice or backup model family.
3. Keep self-hosted vLLM/Qwen only for later private deployment scenarios.

## Recommended Defaults

| Capability | Primary provider | Default model | Backup |
| --- | --- | --- | --- |
| Script generation | Volcengine Ark | `doubao-seed-2-0-pro-260215` | `qwen3.7-plus` |
| Compliance check | Volcengine Ark | `doubao-seed-2-0-pro-260215` | `qwen3.7-plus` |
| Video generation | Volcengine Ark | `doubao-seedance-2-0-260128` | ComfyUI/Wan for private GPU |
| ASR/reference analysis | Volcengine ASR adapter | `volcengine-asr` | Qwen Audio or WhisperX |

## API Base URLs

Volcengine Ark OpenAI-compatible endpoint:

```text
https://ark.cn-beijing.volces.com/api/v3
```

Alibaba Cloud Bailian OpenAI-compatible endpoint:

```text
https://dashscope.aliyuncs.com/compatible-mode/v1
```

## Notes

- The admin console model settings take priority when a saved model has `api_base`, `api_key`, and `model_name`.
- `.env` values are fallback defaults for local or unattended runs.
- The system keeps `stub` as the development default so the full workflow can run without a paid API key.
- For production, create an active script model in System Settings and paste the Volcengine Ark API key.

## Reference Links

- Volcengine Ark documentation: https://www.volcengine.com/docs/82379
- Doubao API documentation: https://www.volcengine.com/docs/6561/1354868
- Alibaba Cloud Model Studio model list: https://help.aliyun.com/zh/model-studio/models
