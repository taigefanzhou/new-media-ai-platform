# 剪辑决策表

在生成或修改 `storyboard_plan` 时使用以下字段。时间单位统一为秒，保留最多三位小数。

```json
{
  "project": {
    "goal": "让酒店管理者理解无感入住的价值",
    "platform": "wechat_channels",
    "aspect_ratio": "9:16",
    "duration_seconds": 30,
    "hook_variants": ["客人没刷卡，房门却自己开了", "一张房卡为什么能让整层断网"]
  },
  "shots": [
    {
      "start_second": 0,
      "end_second": 2.4,
      "shot_type": "close_up",
      "visual": "门锁亮起后自动开门",
      "asset_or_background": "owned hotel smart-lock close-up",
      "source_in_second": 1.2,
      "source_out_second": 3.6,
      "edit_intent": "先展示异常结果形成悬念",
      "transition": "hard_cut",
      "audio_cue": "lock_beep + narration_J_cut",
      "screen_text": "没刷卡，门却开了？",
      "caption_emphasis": ["没刷卡", "开了"],
      "color_note": "neutral warm hotel light; preserve skin tone",
      "needs_lip_sync": false,
      "copyright_status": "owned"
    }
  ],
  "audio": {
    "narration_priority": true,
    "bgm_mood": "restrained technology tension",
    "duck_under_voice": true,
    "sfx_policy": "only actions, alerts and reveals"
  },
  "quality_checks": [
    "hook_clear_without_sound",
    "captions_inside_safe_area",
    "voice_bgm_balance",
    "identity_and_skin_tone_stable",
    "owned_or_licensed_assets_only"
  ]
}
```

## 必填镜头字段

- `start_second`, `end_second`
- `shot_type`, `visual`, `asset_or_background`
- `edit_intent`：解释镜头在叙事中的作用
- `transition`：默认 `hard_cut`，不要随机选择特效
- `audio_cue`：旁白、环境声、BGM或音效节点
- `screen_text`, `caption_emphasis`
- `color_note`
- `needs_lip_sync`
- `copyright_status`

## 校验

- 镜头时间不得倒置或重叠，除非明确放在叠加轨。
- 每个镜头必须有 `edit_intent`；无法说明用途的镜头应删除。
- `reference_only` 和 `blocked` 不得进入成片轨道。
- 字幕文字不得写入视频生成 prompt；由后期字幕轨处理。
- 人物镜头的色彩、美颜和身份要求必须连续。
