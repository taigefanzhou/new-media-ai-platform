from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ModuleAction:
    label: str
    page: str
    intent: str


@dataclass(frozen=True)
class ProductModule:
    key: str
    label: str
    role: str
    summary: str
    page: str
    primary_action: ModuleAction
    stages: tuple[str, ...]
    outputs: tuple[str, ...]
    quality_rules: tuple[str, ...]


PRODUCT_MODULES: tuple[ProductModule, ...] = (
    ProductModule(
        key="reference_video_learning",
        label="参考视频学习生成",
        role="主入口一",
        summary="粘贴视频链接后，系统拆解脚本、拍摄手法、视频结构、字幕设计和吸引观众原因，再生成原创脚本与视频方案。",
        page="analysis",
        primary_action=ModuleAction(label="进入参考视频学习", page="analysis", intent="import_reference"),
        stages=(
            "导入视频链接",
            "解析下载到参考素材库",
            "深度拆解脚本/拍摄/剪辑/字幕",
            "生成原创脚本和分镜方案",
            "选择数字人或背景类成片方式",
            "生成视频并进入视频库",
        ),
        outputs=(
            "参考素材",
            "视频拆解报告",
            "原创脚本候选",
            "分镜执行表",
            "字幕策略",
            "视频任务/成片",
        ),
        quality_rules=(
            "只学习结构和方法，不搬运原文、人物和画面。",
            "生成方案必须包含可执行分镜、素材需求和字幕设计。",
            "成片进入视频库前检查脸部、字幕、水印、脚本一致性。",
        ),
    ),
    ProductModule(
        key="script_direction_creation",
        label="输入方向自动创作",
        role="主入口二",
        summary="输入视频方向或脚本主题，系统自动生成多个脚本、视频结构方案、分镜表和画面提示词。",
        page="creation",
        primary_action=ModuleAction(label="进入内容创作", page="creation", intent="create_from_topic"),
        stages=(
            "输入主题方向",
            "生成脚本候选",
            "生成视频结构和分镜表",
            "选择数字人口播或纯背景/B-roll",
            "生成视频并进入视频库",
        ),
        outputs=(
            "脚本候选",
            "标题和话题",
            "分镜执行表",
            "Seedance/视频模型提示词",
            "视频任务/成片",
        ),
        quality_rules=(
            "脚本必须减少 AI 味，使用自然口播和真实业务场景。",
            "分镜必须能被素材库或视频模型执行。",
            "数字人身份、声音、性别、背景和脚本设定必须一致。",
        ),
    ),
    ProductModule(
        key="asset_and_avatar_library",
        label="素材库与数字人",
        role="基础能力",
        summary="管理头像、口播源视频、产品图、参考素材、B-roll 和数字人认证状态，供两个主入口复用。",
        page="humans",
        primary_action=ModuleAction(label="管理素材和数字人", page="humans", intent="manage_assets"),
        stages=(
            "上传或补传素材",
            "创建数字人资产",
            "完成真人授权/认证",
            "给脚本分镜匹配素材",
        ),
        outputs=(
            "数字人资产",
            "头像/口播源",
            "产品和背景素材",
            "素材匹配记录",
        ),
        quality_rules=(
            "素材必须按账号隔离。",
            "参考素材只能学习结构，不直接搬运成片。",
            "数字人必须授权后再用于正式生成。",
        ),
    ),
    ProductModule(
        key="video_library_and_tasks",
        label="视频库与生成任务",
        role="生产中台",
        summary="集中管理自动生成任务、分段素材、字幕状态、成片预览、审核和入库。",
        page="tasks",
        primary_action=ModuleAction(label="查看视频库", page="tasks", intent="review_videos"),
        stages=(
            "创建视频任务",
            "分段生成/混剪",
            "字幕包装",
            "审核成片",
            "准备发布",
        ),
        outputs=(
            "视频任务",
            "分段视频",
            "字幕成片",
            "审核状态",
            "可发布视频",
        ),
        quality_rules=(
            "任务失败必须可追踪到脚本、分镜、素材或模型步骤。",
            "字幕不能遮挡脸部和核心画面。",
            "审核通过后才进入发布准备。",
        ),
    ),
    ProductModule(
        key="account_publishing",
        label="账号绑定与自动发布",
        role="发布闭环",
        summary="绑定视频号、抖音等平台账号，给审核通过的视频生成标题、简介、话题和发布记录。",
        page="publish",
        primary_action=ModuleAction(label="进入发布中心", page="publish", intent="publish_video"),
        stages=(
            "绑定平台账号",
            "选择成片",
            "准备标题/简介/话题",
            "手动或自动发布",
            "记录发布结果",
        ),
        outputs=(
            "平台账号",
            "发布记录",
            "发布状态",
            "失败原因",
        ),
        quality_rules=(
            "只有审核通过的视频可准备发布。",
            "发布标题和话题必须与脚本内容一致。",
            "发布结果必须留痕，便于复盘。",
        ),
    ),
)


def product_module_manifest() -> list[dict[str, object]]:
    return [asdict(module) for module in PRODUCT_MODULES]
