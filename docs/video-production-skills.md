# 视频生产 Skill

系统已把视频生成从“单次模型调用”升级为内置生产流程：

完整的研究依据和生产决策见 [证据驱动的视频生成与剪辑流程](evidence-based-video-production.md)。

1. 参考视频拆解
2. 原创脚本生成
3. 分镜执行表
4. 素材匹配
5. 视频生成
6. 专业剪辑
7. 字幕包装
8. 质量检查

## 参考视频拆解

参考 OpenMontage、mcptube-vision、VideoAgent 的思路，系统拆解参考视频时会学习 transcript、hook、节奏、关键帧、镜头角色、字幕方式和可复用结构。

约束：

- 只学习结构、节奏、拍摄和剪辑方法。
- 不复刻原视频原文、人物、画面、商家信息。
- 输出必须能指导原创脚本和分镜生成。

## 素材匹配

参考 Jellyfish、VideoAgent 的素材库思路，系统在生成视频任务时会根据分镜的 `visual`、`asset_or_background`、`prompt` 匹配素材库。

约束：

- 优先 `owned` / `licensed` 素材。
- `reference_only` 只能做参考或模型参考，不应直接混剪成片。
- `blocked` 永不使用。

## 脚本分镜

参考 VideoClaw、AI Video Storyboard Skill、Seedance2 API Skill 的结构，脚本生成必须输出可执行的 `storyboard_plan`。

每段必须包含：

- `start_second`
- `end_second`
- `shot_type`
- `visual`
- `person_action`
- `screen_text`
- `asset_or_background`
- `ai_prompt`
- `needs_lip_sync`

视频模型提示词要求：

- 英文 prompt。
- 明确画幅和真人质感。
- `clean plate`
- `no on-screen text`
- `no watermark`
- `consistent background`
- 自然表情、自然口型、自然手势。
- 每镜一个叙事意图、一个主动作、一个运镜、一个结束状态。
- 参考图、参考视频和参考音频各自只承担一个主要控制职责。

## 剪映专业剪辑导演

项目级 Skill 位于 `skills/jianying-professional-editor/`。它把每段分镜补充为可审计的剪辑决策表，并按以下顺序执行：

1. 旁白和主叙事粗剪。
2. 语义匹配 B-roll 与 J/L Cut 声音衔接。
3. 字幕、BGM、环境声和关键音效。
4. 轻度曝光、白平衡、肤色和镜头匹配。
5. 前3秒、同步、黑帧、字幕安全区、人物稳定和版权质检。

剪映10.9 Mac 端只使用真实 UI 自动化，不读写加密草稿。素材必须从“已添加素材”缩略图中心长按后拖入主时间线，框选不视为入轨。

## 视频质检

参考 VBench、VideoScore2 和系统事故记录，成片后至少检查：

- 底片无内嵌大字、标题、贴纸、Logo、UI、水印。
- 脸部、嘴形、眼睛、手势和身体无明显抖动、乱码或撕裂。
- 背景、人物身份、音色、性别和脚本设定保持一致。
- 字幕由系统后期添加，中文正常显示，不遮脸、不用粗暴黑块。
- 画面内容和口播脚本一致，参考素材不侵权、不复刻。
- 分别输出人物真实性、脚本对齐、时序一致、物理合理、文字水印、音频字幕结果，不用单一总分掩盖严重缺陷。

## 接入位置

- `backend/app/services/video_skills.py`：统一 Skill 定义。
- `backend/app/services/ai_clients.py`：脚本和分镜生成 prompt。
- `backend/app/services/video_analysis.py`：参考视频拆解 prompt 和本地分析结果。
- `backend/app/services/pipeline.py`：素材匹配和任务审计备注。
- `GET /api/video-production-skills`：前端展示当前启用 Skill。
