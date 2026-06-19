# Trending Collection Plan

Trending collection is not solved by an LLM alone.

The production architecture should be:

1. Collect structured video references from a compliant data source or a company-owned adapter.
2. Store title, author, URL, metrics, hook, summary, tags, and compliance notes.
3. Use an LLM to analyze the collected references and extract reusable content patterns.
4. Generate original topics and scripts from the pattern analysis, not by copying captions or footage.

## Recommended Data Source Layer

Use one of these approaches:

- Official/open-platform API where available for authorized account data.
- A paid third-party trend data provider with a lawful API.
- A private internal adapter that your team operates and monitors.
- Manual reference entry for early testing.

The current backend already supports an HTTP JSON adapter shape:

```text
POST {api_base}/trending/search
```

Payload:

```json
{
  "platform": "douyin",
  "keyword": "hotel smart energy",
  "category": "hospitality",
  "limit": 20
}
```

Expected response can be a list or an object containing `items`, `videos`, `data`, `results`, or `list`.

## Recommended Model Layer

Use models after collection:

| Task | Recommended model |
| --- | --- |
| Hook and structure analysis | Volcengine Ark Doubao Seed 2.0 Pro |
| Long reference summaries | Qwen knowledge/docs/long-context model |
| Compliance rewrite | Volcengine Ark Doubao Seed 2.0 Pro |
| Original script generation | Volcengine Ark Doubao Seed 2.0 Pro |

## Compliance Notes

- Do not directly copy captions, scripts, watermarked videos, or creator footage.
- Use reference videos for topic direction, structure, and market signals only.
- Keep source URLs and compliance notes with every reference record.
