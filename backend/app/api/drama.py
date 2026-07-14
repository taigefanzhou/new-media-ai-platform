from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.api.access import _assign_owner, _ensure_record_access, _owned_statement, _require_write_user
from app.api.video_tasks_support import _build_video_task
from app.core.auth import current_user
from app.core.db import get_session
from app.models.drama import DramaCharacter, DramaProject, DramaScene, DramaShot
from app.models.entities import Material, Script, User, VideoTask


class DramaProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    premise: str = ""
    visual_style: str = ""
    narrator_human_id: Optional[int] = None


class DramaCharacterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    role: str = ""
    visual_prompt: str = ""
    costume_prompt: str = ""
    voice_human_id: Optional[int] = None
    reference_material_id: Optional[int] = None


class DramaSceneCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    visual_prompt: str = ""
    reference_material_id: Optional[int] = None


class DramaShotCreate(BaseModel):
    scene_id: Optional[int] = None
    duration_seconds: int = Field(default=5, ge=3, le=10)
    beat: str = ""
    dialogue: str = ""
    visual_prompt: str = ""
    character_ids: list[int] = Field(default_factory=list)
    reference_material_id: Optional[int] = None


class DramaShotUpdate(BaseModel):
    scene_id: Optional[int] = None
    duration_seconds: Optional[int] = Field(default=None, ge=3, le=10)
    beat: Optional[str] = None
    dialogue: Optional[str] = None
    visual_prompt: Optional[str] = None
    character_ids: Optional[list[int]] = None
    reference_material_id: Optional[int] = None


def _project_bundle(session: Session, project: DramaProject) -> dict[str, object]:
    return {
        "project": project,
        "characters": list(session.exec(select(DramaCharacter).where(DramaCharacter.project_id == project.id).order_by(DramaCharacter.id)).all()),
        "scenes": list(session.exec(select(DramaScene).where(DramaScene.project_id == project.id).order_by(DramaScene.id)).all()),
        "shots": list(session.exec(select(DramaShot).where(DramaShot.project_id == project.id).order_by(DramaShot.order_index, DramaShot.id)).all()),
    }


def _project(session: Session, project_id: int, user: User, write: bool = False) -> DramaProject:
    project = session.get(DramaProject, project_id)
    return _ensure_record_access(project, user, "Drama project", write=write)


def _optional_material(session: Session, material_id: Optional[int], user: User) -> Optional[Material]:
    if material_id is None:
        return None
    return _ensure_record_access(session.get(Material, material_id), user, "Reference material")


def list_drama_projects(session: Session = Depends(get_session), user: User = Depends(current_user)) -> list[DramaProject]:
    return list(session.exec(_owned_statement(select(DramaProject).order_by(DramaProject.updated_at.desc()), DramaProject, user)).all())


def create_drama_project(payload: DramaProjectCreate, session: Session = Depends(get_session), user: User = Depends(current_user)) -> DramaProject:
    _require_write_user(user)
    project = DramaProject.model_validate(payload)
    _assign_owner(project, user)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def get_drama_project(project_id: int, session: Session = Depends(get_session), user: User = Depends(current_user)) -> dict[str, object]:
    return _project_bundle(session, _project(session, project_id, user))


def create_drama_character(project_id: int, payload: DramaCharacterCreate, session: Session = Depends(get_session), user: User = Depends(current_user)) -> DramaCharacter:
    _require_write_user(user)
    _project(session, project_id, user, write=True)
    _optional_material(session, payload.reference_material_id, user)
    character = DramaCharacter(project_id=project_id, **payload.model_dump())
    _assign_owner(character, user)
    session.add(character)
    session.commit()
    session.refresh(character)
    return character


def create_drama_scene(project_id: int, payload: DramaSceneCreate, session: Session = Depends(get_session), user: User = Depends(current_user)) -> DramaScene:
    _require_write_user(user)
    _project(session, project_id, user, write=True)
    _optional_material(session, payload.reference_material_id, user)
    scene = DramaScene(project_id=project_id, **payload.model_dump())
    _assign_owner(scene, user)
    session.add(scene)
    session.commit()
    session.refresh(scene)
    return scene


def create_drama_shot(project_id: int, payload: DramaShotCreate, session: Session = Depends(get_session), user: User = Depends(current_user)) -> DramaShot:
    _require_write_user(user)
    _project(session, project_id, user, write=True)
    _optional_material(session, payload.reference_material_id, user)
    order_index = len(session.exec(select(DramaShot).where(DramaShot.project_id == project_id)).all()) + 1
    shot = DramaShot(
        project_id=project_id,
        order_index=order_index,
        **payload.model_dump(exclude={"character_ids"}),
        character_ids_json=json.dumps(payload.character_ids),
    )
    _assign_owner(shot, user)
    session.add(shot)
    session.commit()
    session.refresh(shot)
    return shot


def update_drama_shot(shot_id: int, payload: DramaShotUpdate, session: Session = Depends(get_session), user: User = Depends(current_user)) -> DramaShot:
    shot = _ensure_record_access(session.get(DramaShot, shot_id), user, "Drama shot", write=True)
    values = payload.model_dump(exclude_unset=True)
    if "reference_material_id" in values:
        _optional_material(session, values["reference_material_id"], user)
    if "character_ids" in values:
        shot.character_ids_json = json.dumps(values.pop("character_ids"))
    for name, value in values.items():
        setattr(shot, name, value)
    shot.updated_at = datetime.utcnow()
    session.add(shot)
    session.commit()
    session.refresh(shot)
    return shot


def bootstrap_cloud_hotel(project_id: int, session: Session = Depends(get_session), user: User = Depends(current_user)) -> dict[str, object]:
    project = _project(session, project_id, user, write=True)
    if session.exec(select(DramaShot).where(DramaShot.project_id == project.id)).first():
        raise HTTPException(status_code=409, detail="项目已有镜头，不能重复套用示例模板。")

    project.premise = project.premise or "未来云端酒店的智能客控运维员，在悬浮套房排查身份权限异常。"
    project.visual_style = project.visual_style or "9:16 手机 Vlog 质感，未来云端酒店，金白色云海，真实人物，稳定面部，电影级晨光，无屏幕文字，无水印。"
    characters = [
        DramaCharacter(project_id=project.id or 0, name="林一", role="酒店智能客控运维员", visual_prompt="25岁中国男性，黑色工装和银灰工具背心，手持智能门锁诊断器，亲和自然的手机 Vlog 主角", costume_prompt="黑色工装，银灰工具背心"),
        DramaCharacter(project_id=project.id or 0, name="云栖", role="原创旅行体验官", visual_prompt="年轻中国女性，白色未来感旅行服，轻便行李，友好而好奇", costume_prompt="白色未来旅行服"),
        DramaCharacter(project_id=project.id or 0, name="小栈", role="原创机器人管家", visual_prompt="圆润小型悬浮机器人，暖金色指示灯，简洁可信赖", costume_prompt="无"),
    ]
    scene = DramaScene(project_id=project.id or 0, name="未来云端酒店", visual_prompt="悬浮在云海之上的未来酒店大堂和走廊，金白色建筑，通透玻璃，清晨阳光，轻雾")
    for item in [*characters, scene]:
        _assign_owner(item, user)
        session.add(item)
    session.commit()
    for item in characters:
        session.refresh(item)
    session.refresh(scene)

    beat_sheet = [
        (5, "反差钩子", "在云端酒店做智能客控运维，到底是什么体验？", "林一自拍中近景，身后是云海上的未来酒店门厅，手机 Vlog 广角，顶部留出标题安全区", [characters[0].id]),
        (8, "任务铺垫", "今天得给悬浮套房部署无感入住，顺便排查一条异常报警。", "林一举起智能门锁诊断器特写，镜头切回云端酒店走廊，人物和场景保持一致", [characters[0].id]),
        (8, "工具证明", "旅客身份、房门权限、室内设备，全都得在三秒内确认。", "诊断器光线扫描门牌，林一在镜头右侧讲解，干净的未来酒店门口", [characters[0].id]),
        (8, "爆点人物", "咦，体验官云栖怎么提前到了？", "林一回头，云栖从走廊另一端进入画面，平视同框，轻微手持 Vlog 感", [characters[0].id, characters[1].id]),
        (8, "互动推进", "她刚刷脸进门，整层房间却突然切进隐私保护模式。", "云栖困惑地看向悬浮门牌，小栈机器人亮起暖金色警示灯，保持人物造型一致", [characters[0].id, characters[1].id, characters[2].id]),
        (8, "冲突升级", "不是系统宕机，是有人拿到了错误的临时权限。", "林一快速查看诊断器，走廊灯光轻微切换，画面保持明亮稳定，不出现真实品牌界面", [characters[0].id]),
        (8, "解决动作", "先锁住公共区域，再把云栖的权限回滚。", "林一操作诊断器，小栈投射简洁的无文字光圈，云栖站在安全距离外", [characters[0].id, characters[1].id, characters[2].id]),
        (7, "下集钩子", "等等，总控中心提示：顶层总统套房的监控，离线了。", "林一表情从放松转为震惊，镜头推近；远处顶层建筑亮起红色警示灯，留悬念", [characters[0].id]),
    ]
    for index, (duration, beat, dialogue, visual, character_ids) in enumerate(beat_sheet, start=1):
        shot = DramaShot(project_id=project.id or 0, scene_id=scene.id, order_index=index, duration_seconds=duration, beat=beat, dialogue=dialogue, visual_prompt=visual, character_ids_json=json.dumps(character_ids))
        _assign_owner(shot, user)
        session.add(shot)
    project.updated_at = datetime.utcnow()
    session.add(project)
    session.commit()
    return _project_bundle(session, project)


def build_drama_video_task(project_id: int, session: Session = Depends(get_session), user: User = Depends(current_user)) -> dict[str, object]:
    project = _project(session, project_id, user, write=True)
    shots = list(session.exec(select(DramaShot).where(DramaShot.project_id == project_id).order_by(DramaShot.order_index, DramaShot.id)).all())
    if not shots:
        raise HTTPException(status_code=400, detail="请先至少添加一个短剧镜头。")
    characters = {item.id: item for item in session.exec(select(DramaCharacter).where(DramaCharacter.project_id == project_id)).all()}
    scenes = {item.id: item for item in session.exec(select(DramaScene).where(DramaScene.project_id == project_id)).all()}
    storyboard_plan: list[dict[str, object]] = []
    start_second = 0
    voiceover: list[str] = []
    for shot in shots:
        scene = scenes.get(shot.scene_id)
        cast = [characters.get(item) for item in json.loads(shot.character_ids_json or "[]")]
        cast_prompt = "；".join(item.visual_prompt for item in cast if item)
        reference_material_id = shot.reference_material_id or (scene.reference_material_id if scene else None) or next((item.reference_material_id for item in cast if item and item.reference_material_id), None)
        visual = "；".join(part for part in (project.visual_style, scene.visual_prompt if scene else "", cast_prompt, shot.visual_prompt) if part)
        end_second = start_second + shot.duration_seconds
        storyboard_plan.append({
            "start_second": start_second,
            "end_second": end_second,
            "shot_type": shot.beat or "drama_shot",
            "visual": visual,
            "person_action": shot.beat,
            "screen_text": "",
            "asset_or_background": scene.name if scene else "短剧场景",
            "ai_prompt": visual,
            "needs_lip_sync": False,
            "reference_material_id": reference_material_id,
        })
        voiceover.append(shot.dialogue or shot.beat)
        start_second = end_second
    script = Script(
        target_platform="wechat_channels",
        duration_seconds=start_second,
        hook=shots[0].dialogue or project.title,
        voiceover="\n".join(item for item in voiceover if item),
        storyboard="\n".join(f"{index + 1}. {shot.visual_prompt}" for index, shot in enumerate(shots)),
        storyboard_plan=json.dumps(storyboard_plan, ensure_ascii=False),
        seedance_prompt=project.visual_style,
        title_options=project.title,
        hashtags="#短剧 #原创剧情 #未来酒店",
        compliance_notes="原创世界观和角色设定；仅复用参考视频的节奏与结构，不复用人物、台词、场景或剧情。",
    )
    _assign_owner(script, user)
    session.add(script)
    session.commit()
    session.refresh(script)
    task = _build_video_task(script, project.narrator_human_id, production_mode="seedance_scene", target_platform="wechat_channels", export_profile="wechat_channels_portrait", subtitle_enabled=True, subtitle_style="auto", owner=user)
    task.audit_notes = f"短剧项目 #{project.id}《{project.title}》生成任务：镜头参考图优先进入 Seedance 逐镜头生成；任务默认不自动执行。"
    session.add(task)
    session.flush()
    project.latest_video_task_id = task.id
    project.updated_at = datetime.utcnow()
    session.add(project)
    session.commit()
    session.refresh(task)
    session.refresh(script)
    session.refresh(project)
    return {
        "script": script.model_dump(),
        "video_task": task.model_dump(),
        "project": project.model_dump(),
    }
