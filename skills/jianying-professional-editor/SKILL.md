---
name: jianying-professional-editor
description: Plan, execute, and quality-check professional short-form edits using this system's scripts, digital humans, generated footage, owned media library, and JianYing Pro on macOS. Use for 剪映专业剪辑、粗剪、精剪、短剧、口播、B-roll、字幕包装、配乐音效、J/L Cut、关键帧、轻度调色、竖屏短视频、自动导出，或把系统生成素材整理为可发布成片。适配当前 Mac 剪映专业版10.9；不要依赖旧版明文草稿。
---

# 剪映专业剪辑导演

把模型生成的素材变成有叙事、有节奏、可验收的成片。先做剪辑决策，再操作剪映。

## 工作流

1. 明确目标：平台、画幅、时长、受众、单一传播目标和版权范围。
2. 检查输入：脚本、旁白、人物、素材、音乐、参考视频和系统 `storyboard_plan`。
3. 阅读 [editing-rules.md](references/editing-rules.md)，按内容类型制定粗剪和精剪策略。
4. 按 [edit-plan-schema.md](references/edit-plan-schema.md) 输出可执行剪辑决策表。每个镜头必须说明选它的理由。
5. 先完成旁白和主叙事粗剪，再依次处理 B-roll、声音衔接、字幕、音乐音效、轻度调色和关键帧。
6. 在 Mac 剪映10.9执行时阅读 [jianying-macos-10.9.md](references/jianying-macos-10.9.md)。使用真实 UI，不读写加密草稿。
7. 导出后执行验收清单；不合格时定位到具体镜头重剪，不整片盲目重做。

## 决策规则

- 前3秒先给结果、冲突、异常或明确利益点；删除问候、Logo片头和空泛铺垫。
- 画面变化必须对应信息变化。不要为了“热闹”机械地每秒切镜头。
- 对话或旁白跨镜头时优先用 J/L Cut 保持连续；转场必须表达时间、空间或情绪变化。
- B-roll 必须与当前台词语义一致，且只使用 `owned` / `licensed` 素材；`reference_only` 不进入成片。
- 字幕按语义断句，校对人名、数字和术语；关键词高亮克制，不遮挡脸和关键物体。
- 人声优先。说话时压低 BGM，音效只强调真正的动作、转折和提示。
- 人像只做自然修饰：统一白平衡、曝光和肤色，禁止改变身份、年龄或五官。
- 特效、滤镜、花字和运镜都必须有叙事理由；无法说明用途就删除。

## 系统接入

- 从 `/api/video-production-skills` 获取启用的能力和质量要求。
- 使用现有 `storyboard_plan` 作为剪辑决策载体，并补齐 `edit_intent`、`transition`、`audio_cue`、`color_note` 和 `caption_emphasis`。
- 素材生成、数字人、TTS、字幕和质检继续走系统现有模型接口。
- 本机执行复用项目脚本 `scripts/jianying_mac_automation.swift`，不要复制执行代码到 Skill。

## 验收

- 第一帧和前三秒能在静音状态下说明主题与继续观看的理由。
- 旁白、人物口型、字幕、B-roll和声音节点同步。
- 无黑帧、空轨、重复镜头、跳帧、字幕遮脸、爆音、第三方水印或参考素材搬运。
- 人物身份、年龄感、肤色、发型、服装和声音在连续镜头中稳定。
- 输出画幅、分辨率、帧率、时长和平台安全区符合目标平台。
- 保留剪辑决策表、素材来源和质检结果，便于失败镜头单独返工。
