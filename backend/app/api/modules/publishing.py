from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.api.access import (
    _assign_owner,
    _ensure_record_access,
    _owned_statement,
    _require_write_user,
)
from app.api.publishing_support import (
    _clear_default_account,
    _ensure_publish_ready,
    _parse_optional_datetime,
    _resolve_publish_account,
    _set_publish_status,
)
from app.core.auth import current_user
from app.core.db import get_session
from app.models.entities import PlatformAccount, PublishRecord, Script, User, VideoTask
from app.schemas.requests import PlatformAccountCreate, PlatformAccountUpdate, PublishPrepareRequest, PublishRecordUpdate


router = APIRouter(tags=["账号绑定与自动发布"])


def prepare_publish_record(
    payload: PublishPrepareRequest,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> PublishRecord:
    task = session.get(VideoTask, payload.video_task_id)
    _ensure_record_access(task, user, "Video task")
    script = session.get(Script, task.script_id)
    account = _resolve_publish_account(session, payload.platform_account_id, payload.platform, user=user)
    _ensure_publish_ready(session, task, script, payload.title, account)
    record = PublishRecord(
        video_task_id=payload.video_task_id,
        platform=account.platform if account else payload.platform,
        platform_account_id=account.id if account else payload.platform_account_id,
        account_name=account.account_name if account else payload.account_name,
        title=payload.title,
        hashtags=payload.hashtags,
        caption=payload.caption,
        scheduled_at=_parse_optional_datetime(payload.scheduled_at),
        publish_status="prepared",
    )
    _assign_owner(record, user)
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def list_publish_records(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[PublishRecord]:
    statement = _owned_statement(select(PublishRecord).order_by(PublishRecord.created_at.desc()), PublishRecord, user)
    return list(session.exec(statement).all())


def update_publish_record(
    record_id: int,
    payload: PublishRecordUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> PublishRecord:
    record = session.get(PublishRecord, record_id)
    _ensure_record_access(record, user, "Publish record", write=True)
    update_data = payload.model_dump(exclude_unset=True)
    if "platform_account_id" in update_data:
        account_id = update_data.pop("platform_account_id")
        if account_id is None:
            record.platform_account_id = None
            if "account_name" not in update_data:
                record.account_name = None
        else:
            account = _resolve_publish_account(session, account_id, update_data.get("platform"), user=user)
            if account is not None:
                record.platform = account.platform
                record.platform_account_id = account.id
                record.account_name = account.account_name
    for key in ("scheduled_at", "published_at"):
        if key in update_data:
            update_data[key] = _parse_optional_datetime(update_data[key])
    for key, value in update_data.items():
        setattr(record, key, value)
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def mark_publish_record_published(
    record_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> PublishRecord:
    record = session.get(PublishRecord, record_id)
    _ensure_record_access(record, user, "Publish record")
    task = session.get(VideoTask, record.video_task_id)
    _ensure_record_access(task, user, "Video task")
    script = session.get(Script, task.script_id)
    account = session.get(PlatformAccount, record.platform_account_id) if record.platform_account_id else None
    _ensure_publish_ready(session, task, script, record.title, account)
    return _set_publish_status(session, record_id, "published", datetime.utcnow(), user=user)


def mark_publish_record_failed(
    record_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> PublishRecord:
    return _set_publish_status(session, record_id, "failed", user=user)


def cancel_publish_record(
    record_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> PublishRecord:
    return _set_publish_status(session, record_id, "canceled", user=user)


def create_platform_account(
    payload: PlatformAccountCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> PlatformAccount:
    _require_write_user(user)
    if payload.is_default:
        _clear_default_account(session, payload.platform, user=user)
    account = PlatformAccount.model_validate(payload)
    _assign_owner(account, user)
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


def list_platform_accounts(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[PlatformAccount]:
    statement = _owned_statement(
        select(PlatformAccount).order_by(
            PlatformAccount.is_default.desc(),
            PlatformAccount.created_at.desc(),
        ),
        PlatformAccount,
        user,
    )
    return list(session.exec(statement).all())


def update_platform_account(
    account_id: int,
    payload: PlatformAccountUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> PlatformAccount:
    account = session.get(PlatformAccount, account_id)
    _ensure_record_access(account, user, "Platform account", write=True)
    update_data = payload.model_dump(exclude_unset=True)
    next_platform = update_data.get("platform", account.platform)
    if update_data.get("is_default") is True:
        _clear_default_account(session, next_platform, user=user)
    for key, value in update_data.items():
        setattr(account, key, value)
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


def set_default_platform_account(
    account_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> PlatformAccount:
    account = session.get(PlatformAccount, account_id)
    _ensure_record_access(account, user, "Platform account", write=True)
    _clear_default_account(session, account.platform, user=user)
    account.is_default = True
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


router.post("/publish-records", response_model=PublishRecord)(prepare_publish_record)
router.get("/publish-records", response_model=list[PublishRecord])(list_publish_records)
router.patch("/publish-records/{record_id}", response_model=PublishRecord)(update_publish_record)
router.post("/publish-records/{record_id}/mark-published", response_model=PublishRecord)(mark_publish_record_published)
router.post("/publish-records/{record_id}/fail", response_model=PublishRecord)(mark_publish_record_failed)
router.post("/publish-records/{record_id}/cancel", response_model=PublishRecord)(cancel_publish_record)
router.post("/platform-accounts", response_model=PlatformAccount)(create_platform_account)
router.get("/platform-accounts", response_model=list[PlatformAccount])(list_platform_accounts)
router.patch("/platform-accounts/{account_id}", response_model=PlatformAccount)(update_platform_account)
router.post("/platform-accounts/{account_id}/set-default", response_model=PlatformAccount)(set_default_platform_account)
