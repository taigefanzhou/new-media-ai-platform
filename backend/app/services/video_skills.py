from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class VideoProductionSkill:
    key: str
    label: str
    source: str
    summary: str
    workflow_rules: tuple[str, ...]
    quality_checks: tuple[str, ...]


VIDEO_PRODUCTION_SKILLS: tuple[VideoProductionSkill, ...] = (
    VideoProductionSkill(
        key="reference_video_analysis",
        label="参考视频拆解",
        source="OpenMontage / mcptube-vision / VideoAgent",
        summary="分析参考视频的逐字稿、节奏、关键帧、镜头角色和字幕方式，只学习结构，不搬运原文或画面。",
        workflow_rules=(
            "拆解 transcript、hook、scene pacing、keyframes、shot roles、caption style。",
            "输出可复用模板时必须区分可学习结构和不可搬运内容。",
            "参考素材仅作为结构/节奏/镜头语言来源，不能直接生成同款文案或复刻人物画面。",
        ),
        quality_checks=(
            "是否识别开头钩子、视觉变化频率和镜头功能。",
            "是否明确标注不可搬运的原视频元素。",
            "是否能直接指导原创脚本和分镜生成。",
        ),
    ),
    VideoProductionSkill(
        key="asset_selection",
        label="素材匹配",
        source="VideoAgent / Jellyfish",
        summary="先理解素材库，再按分镜匹配数字人、背景、B-roll、产品图、参考视频和版权状态。",
        workflow_rules=(
            "优先选择 owned/licensed 素材；reference_only 只能做参考或模型参考，不应原样成片。",
            "每个分镜必须写清 asset_or_background，便于素材库检索。",
            "缺素材时才交给视频模型补镜头，并在审计备注里说明。",
        ),
        quality_checks=(
            "是否使用了同账号可访问素材。",
            "是否避免把参考素材当成版权素材直接混剪。",
            "是否给缺素材镜头留下可追踪原因。",
        ),
    ),
    VideoProductionSkill(
        key="storyboard_generation",
        label="脚本分镜",
        source="VideoClaw / AI Video Storyboard Skill / Seedance2 skill",
        summary="把主题变成可执行的口播稿、镜头表、素材清单、Seedance 英文提示词和后期字幕策略。",
        workflow_rules=(
            "storyboard_plan 必须包含 start_second/end_second/shot_type/visual/person_action/screen_text/asset_or_background/ai_prompt/needs_lip_sync。",
            "多个 5-15 秒镜头必须共享视觉主题、灯光、人物动作尺度和字幕语言，不能像不同视频拼接。",
            "Seedance 提示词使用英文，明确画幅、真人质感、自然动作、无水印、无画面内文字。",
        ),
        quality_checks=(
            "镜头时长是否可执行，长视频是否拆成足够段落。",
            "口播、画面、屏幕文字是否一一对应。",
            "是否避免 AI 腔、塑料皮肤、机械动作和随机换背景。",
        ),
    ),
    VideoProductionSkill(
        key="video_quality_guard",
        label="视频质检",
        source="VBench / VideoScore2 / 本系统事故记录",
        summary="成片后按视觉质量、脚本对齐、物理合理性、脸部稳定、字幕和水印做可解释检查。",
        workflow_rules=(
            "底片不允许模型生成大字、Logo、贴纸、UI 或第三方水印；字幕必须由系统后期统一添加。",
            "数字人视频优先检查脸、嘴、眼、手势和背景稳定性。",
            "生成失败或质量异常必须能回溯到分镜、素材、模型和字幕步骤。",
        ),
        quality_checks=(
            "脸部/嘴形是否抖动、乱码或过度美颜。",
            "脚本内容、字幕和视频画面是否一致。",
            "字幕是否可读、无遮挡、无方块字、无粗暴黑块。",
            "背景是否随机跳变，是否出现无关素材或水印。",
        ),
    ),
)


def video_skill_manifest() -> list[dict[str, object]]:
    return [asdict(skill) for skill in VIDEO_PRODUCTION_SKILLS]


def skill_prompt_payload() -> dict[str, object]:
    return {
        "enabled": True,
        "skills": video_skill_manifest(),
        "global_rules": [
            "生成链路必须先结构化，再生成媒体：参考拆解 -> 原创脚本 -> 分镜执行表 -> 素材匹配 -> 视频生成 -> 字幕包装 -> 质量检查。",
            "不能把参考视频的原文、人物、商家信息或画面直接搬进新视频。",
            "所有视频模型 prompt 都应优先生成干净底片，字幕和标题由系统后期完成。",
            "当选择数字人口播时，性别、音色和数字人身份必须一致，不能用女性音频驱动男性数字人。",
        ],
    }


def script_generation_requirements() -> list[str]:
    return [
        "必须启用内置视频生产 Skill：参考视频拆解、素材匹配、脚本分镜、视频质检。",
        "如果 topic 包含参考视频分析，必须只学习结构、节奏、镜头功能、字幕方式，不复刻原视频文案或人物画面。",
        "storyboard_plan 每段必须能被素材匹配器检索：asset_or_background 写具体素材类型、场景、产品或背景。",
        "每个 ai_prompt 必须包含 clean plate / no on-screen text / no watermark / consistent background / natural human motion。",
        "字幕内容只能进入 screen_text 和后期字幕，不允许写入视频模型画面内文字。",
        "数字人口播必须保持人物、性别、声音、动作和背景稳定，不能无理由切换多个背景。",
    ]


def reference_analysis_requirements() -> list[str]:
    return [
        "按参考视频拆解 Skill 输出：hook、节奏、镜头角色、字幕样式、关键帧、可复用模板。",
        "明确区分可学习和不可搬运：结构可学，原文、人物、商家、画面不可搬。",
        "给出原创复用方式：如何换成自己的行业素材、口播观点、背景和字幕策略。",
        "输出质量分时参考 VBench/VideoScore2 思路：结构可用性、视觉可读性、脚本对齐、物理/动作合理性。",
    ]


def material_selection_rules() -> list[str]:
    return [
        "优先 owned/licensed 素材，其次 reference_only 作为模型参考；blocked 永不使用。",
        "匹配维度包括素材名称、标签、类型、分镜 visual、asset_or_background 和 prompt。",
        "酒店/客房/大堂/办公室/后台/看板类分镜优先找真实视频或图片素材。",
        "数字人头像和口播源只用于授权数字人，不作为普通 B-roll 混剪素材。",
    ]


def quality_guard_checklist() -> list[str]:
    return [
        "底片无内嵌大字、标题、贴纸、Logo、UI、水印。",
        "脸部、嘴形、眼睛、手势和身体无明显抖动、乱码或撕裂。",
        "背景、人物身份、音色、性别和脚本设定保持一致。",
        "字幕由系统后期添加，中文正常显示，不遮脸、不用粗暴黑块。",
        "画面内容和口播脚本一致，参考素材不侵权、不复刻。",
    ]
