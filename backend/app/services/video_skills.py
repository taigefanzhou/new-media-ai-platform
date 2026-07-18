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
        key="he_yiyi_hotel_talking",
        label="何依依酒店干货口播",
        source="参考拆解 #8 / 素材 #12",
        summary="固定机位竖版人物口播，顶部常驻两行主题、底部单行逐句字幕，并在参考时间点穿插自有酒店实景和系统画面。",
        workflow_rules=(
            "画幅固定 9:16；人物使用已授权数字人和重建的干净机位底图，参考人物与原文字层不进入成片。",
            "时间轴按固定人物、顶部短插、固定人物、全屏实景、固定人物、顶部系统画面、固定人物收束执行。",
            "配音先生成，数字人口型、单行字幕、B-roll、音乐和轻转场音效跟随参考时间比例。",
        ),
        quality_checks=(
            "人物身份和音色一致，口型稳定，背景不跳变。",
            "字幕不遮脸、不溢出，关键词高亮与口播同步。",
            "只使用 owned/licensed 素材，成片包含有效视频和音轨且无异常黑帧。",
        ),
    ),
    VideoProductionSkill(
        key="reference_video_analysis",
        label="参考视频深度拆解 V2",
        source="DeepVideoDiscovery / Shot2Story / video-use / 本系统证据复核",
        summary="先完成全片脚本与镜头拆解，再复查钩子、转折、证据、高潮和行动引导，把结论绑定到时间点和音视频证据。",
        workflow_rules=(
            "第一轮拆解 transcript、hook、scene pacing、keyframes、shot roles、caption style 和 edit plan。",
            "第二轮重新查看关键片段，核对口播、画面文字、人物动作和声音证据；看不清或听不清时明确标记。",
            "留存评分只表达内容结构的作用强度，不伪造真实播放、完播或用户行为数据。",
            "输出可复用模板时必须区分可学习结构和不可搬运内容。",
            "参考素材仅作为结构/节奏/镜头语言来源，不能直接生成同款文案或复刻人物画面。",
        ),
        quality_checks=(
            "是否识别开头钩子、视觉变化频率和镜头功能。",
            "关键结论是否具备时间范围、音视频证据和置信度。",
            "是否发现并修正第一轮与视频证据矛盾的结论。",
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
            "8-15 秒真人单镜头最多安排一个主动作；人物行走口播时，道具和背景保持静止，不再叠加回头、定时亮灯或表情突变。",
        ),
        quality_checks=(
            "镜头时长是否可执行，长视频是否拆成足够段落。",
            "口播、画面、屏幕文字是否一一对应。",
            "是否避免 AI 腔、塑料皮肤、机械动作和随机换背景。",
        ),
    ),
    VideoProductionSkill(
        key="jianying_professional_editing",
        label="剪映专业剪辑导演",
        source="项目 Skill / CapCut 官方 / Adobe J-L Cut / DaVinci 专业训练",
        summary="先生成可审计的剪辑决策表，再按粗剪、声音衔接、B-roll、字幕、音频、轻调色和质检顺序完成剪映成片。",
        workflow_rules=(
            "前3秒先给结果、冲突、异常或利益点；删除问候、Logo片头、重复表达和无效停顿。",
            "每个分镜补齐 edit_intent、transition、audio_cue、color_note、caption_emphasis；无法说明叙事作用的镜头删除。",
            "对话和旁白跨镜头优先使用 J/L Cut；B-roll 与当前台词语义一致，显式转场只用于时间、空间或情绪变化。",
            "Mac 剪映10.9只通过真实 UI 执行，不读写加密草稿；素材必须从缩略图中心长按拖入主时间线。",
        ),
        quality_checks=(
            "静音查看前三秒仍能理解主题、受众和继续观看的理由。",
            "人物、旁白、字幕、B-roll、音乐和音效节点同步，BGM不遮盖人声。",
            "调色和美颜保持真实身份、年龄感和肤色，镜头间无明显跳色。",
            "无黑帧、空轨、重复镜头、字幕遮脸、爆音、第三方水印或参考素材搬运。",
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
            "生成链路必须先结构化，再生成媒体：参考拆解 -> 原创脚本 -> 分镜执行表 -> 素材匹配 -> 视频生成 -> 专业剪辑 -> 字幕包装 -> 质量检查。",
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
        "每段 storyboard_plan 必须补齐专业剪辑字段：edit_intent、transition、audio_cue、color_note、caption_emphasis。",
        "transition 默认 hard_cut；只有时间、空间或情绪变化时才使用显式转场，对话和旁白跨镜头优先计划 J/L Cut。",
        "字幕内容只能进入 screen_text 和后期字幕，不允许写入视频模型画面内文字。",
        "数字人口播必须保持人物、性别、声音、动作和背景稳定，不能无理由切换多个背景。",
        "8-15 秒 needs_lip_sync 真人单镜头最多一个主动作：行走口播、回头、操作道具三选一；不得同时加入定时道具变化和表情突变。",
        "如果人物选择行走口播，道具、背景和灯光必须全程静止，双手只做自然轻微摆动；复杂剧情改用静态人物加 B-roll 或拆成独立镜头。",
        "酒店干货口播默认按何依依参考模板组织：定向喊话和利益点 -> 痛点 -> 方法引入 -> 2-4 个动作 -> 真实证据 -> 注意事项 -> 行动引导。",
    ]


def he_yiyi_hotel_template_manifest() -> dict[str, object]:
    return {
        "key": "he_yiyi_hotel_v1",
        "reference_analysis_id": 8,
        "reference_material_id": 12,
        "engineering_timeline": "docs/reference-analysis/he-yiyi-busy-season-exact-v2.json",
        "canvas": {"width": 1080, "height": 1920, "fps": 25, "aspect_ratio": "9:16"},
        "sections": (
            ("固定机位开场", 0, 4, "digital_human"),
            ("顶部短插画面", 4, 8, "owned_broll_overlay"),
            ("固定机位铺垫", 8, 19, "digital_human"),
            ("全屏实景转场", 19, 23, "owned_broll_fullscreen"),
            ("固定机位方法", 23, 33, "digital_human"),
            ("顶部系统画面", 33, 43, "owned_system_overlay"),
            ("固定机位收束", 43, 71, "digital_human"),
        ),
        "identity": {
            "source": "active_volcengine_enterprise_asset_only",
            "fallback": "forbidden",
            "forbidden_material_ids": (10, 25, 31),
        },
        "face_alignment": {
            "reference_canvas": (576, 1024),
            "median_face_box": (226.11, 423.17, 143.10, 143.10),
            "center_tolerance_px": 8,
            "scale_tolerance_ratio": 0.05,
        },
        "title": {"font": "Noto Serif CJK SC", "lines": 2, "position": "top_left", "persistent": True},
        "subtitle": {
            "font": "Noto Serif CJK SC",
            "lines": 1,
            "position": "bottom_center",
            "highlight": "#F2D64B",
            "sync_tolerance_ms": 120,
        },
        "audio": {
            "voice_gender": "female",
            "voice_f0_median_hz": 216.2,
            "speech_rate_chars_per_minute": 303,
            "music": "licensed_reference_or_owned_tempo_match",
            "transition_sfx": True,
        },
        "asset_policy": "owned_or_licensed_only",
    }


def reference_analysis_requirements() -> list[str]:
    return [
        "按参考视频深度拆解 V2 输出：hook、节奏、镜头角色、字幕样式、关键帧、证据、置信度和可复用模板。",
        "短视频执行全片拆解和关键片段复核；长视频先全局扫描，再重点回查钩子、转折、证据、高潮和 CTA。",
        "所有吸引力或留存判断必须说明对应时间点和音视频依据，不得伪造真实平台数据。",
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
