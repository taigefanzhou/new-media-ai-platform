from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from app.api.access import _ensure_record_access, _owned_statement
from app.models.entities import (
    CopyrightStatus,
    DigitalHuman,
    Material,
    PlatformAccount,
    PlatformCredential,
    PublishRecord,
    Script,
    TaskStatus,
    User,
    VideoTask,
)


def _effective_video_output_path(task: VideoTask) -> Optional[str]:
    if task.captioned_output_path:
        path = Path(task.captioned_output_path)
        if path.exists() and path.is_file():
            return task.captioned_output_path
    return task.output_path


def _publish_title_from_script(script: Optional[Script]) -> str:
    if script is None:
        return "待发布视频"
    first_line = script.title_options.splitlines()[0] if script.title_options else ""
    return first_line.replace("1.", "").strip() or script.hook[:40] or "待发布视频"


def _hashtags_from_script(script: Optional[Script]) -> str:
    return script.hashtags if script else ""


def _caption_from_script(script: Optional[Script]) -> str:
    if script is None:
        return ""
    return f"{script.hook}\n\n{script.hashtags}".strip()


def _publish_validation_blockers(
    session: Session,
    task: VideoTask,
    script: Optional[Script],
    title: str | None,
    account: Optional[PlatformAccount] = None,
) -> list[str]:
    blockers: list[str] = []
    if task.status != TaskStatus.approved:
        blockers.append("视频任务必须先审核通过")
    output_path_value = _effective_video_output_path(task)
    if not output_path_value:
        blockers.append("视频任务还没有成片文件")
    elif output_path_value.startswith("mock://"):
        blockers.append("当前成片仍是占位结果，不能发布")
    elif not output_path_value.startswith("http"):
        output_path = Path(output_path_value)
        if not output_path.exists() or not output_path.is_file():
            blockers.append("本地成片文件不存在")
    if not (title or "").strip():
        blockers.append("发布标题不能为空")
    if account is not None and account.status != "active":
        blockers.append("发布账号不是启用状态")

    if script is not None:
        notes = (script.compliance_notes or "").lower()
        blocked_markers = ("不可发布", "禁止发布", "侵权", "未授权", "blocked", "do not publish")
        if any(marker in notes for marker in blocked_markers):
            blockers.append("脚本合规备注包含不可发布风险")

    if task.digital_human_id:
        human = session.get(DigitalHuman, task.digital_human_id)
        for material_id, label in (
            (human.portrait_material_id if human else None, "数字人头像"),
            (human.source_video_material_id if human else None, "数字人口播源视频"),
        ):
            if material_id is None:
                continue
            material = session.get(Material, material_id)
            if material is None:
                blockers.append(f"{label}素材不存在")
            elif material.copyright_status in {CopyrightStatus.blocked, CopyrightStatus.reference_only}:
                blockers.append(f"{label}素材未获得发布授权")
    return blockers


def _ensure_publish_ready(
    session: Session,
    task: VideoTask,
    script: Optional[Script],
    title: str | None,
    account: Optional[PlatformAccount] = None,
) -> None:
    blockers = _publish_validation_blockers(session, task, script, title, account)
    if blockers:
        raise HTTPException(status_code=400, detail="发布前校验未通过：" + "；".join(blockers))


def _parse_optional_datetime(value: Optional[str]):
    if not value:
        return None
    return datetime.fromisoformat(value)


def _resolve_publish_account(
    session: Session,
    account_id: Optional[int],
    platform: Optional[str],
    user: User | None = None,
) -> Optional[PlatformAccount]:
    if account_id is not None:
        account = session.get(PlatformAccount, account_id)
        if user is not None:
            _ensure_record_access(account, user, "Platform account")
        elif account is None:
            raise HTTPException(status_code=404, detail="Platform account not found")
        return account
    if platform is None:
        return None
    statement = select(PlatformAccount).where(
        PlatformAccount.platform == platform,
        PlatformAccount.is_default == True,
    )
    if user is not None:
        statement = _owned_statement(statement, PlatformAccount, user)
    return session.exec(statement).first()


def _clear_default_account(session: Session, platform: str, user: User | None = None) -> None:
    statement = select(PlatformAccount).where(PlatformAccount.platform == platform)
    if user is not None:
        statement = _owned_statement(statement, PlatformAccount, user)
    accounts = session.exec(statement).all()
    for account in accounts:
        account.is_default = False
        session.add(account)


def _set_publish_status(
    session: Session,
    record_id: int,
    status: str,
    published_at: Optional[datetime] = None,
    user: User | None = None,
) -> PublishRecord:
    record = session.get(PublishRecord, record_id)
    if user is not None:
        _ensure_record_access(record, user, "Publish record", write=True)
    elif record is None:
        raise HTTPException(status_code=404, detail="Publish record not found")
    record.publish_status = status
    if published_at is not None:
        record.published_at = published_at
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _active_platform_credential(
    session: Session,
    platform: str,
    purpose: str,
) -> Optional[PlatformCredential]:
    return session.exec(
        select(PlatformCredential).where(
            PlatformCredential.platform == platform,
            PlatformCredential.purpose == purpose,
            PlatformCredential.is_active == True,
        )
    ).first()
