from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.api.access import (
    _assign_owner,
    _ensure_record_access,
    _owned_statement,
    _require_write_user,
)
from app.api.publishing_support import _active_platform_credential
from app.core.auth import current_user
from app.core.db import get_session
from app.models.entities import TaskStatus, TrendingSearch, TrendingVideo, User
from app.schemas.requests import TrendingSearchCreate, TrendingVideoCreate
from app.services.trending import TrendingCollector


router = APIRouter(tags=["主题采集"])


def create_trending_search(
    payload: TrendingSearchCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> TrendingSearch:
    _require_write_user(user)
    search = TrendingSearch.model_validate(payload)
    _assign_owner(search, user)
    session.add(search)
    session.commit()
    session.refresh(search)
    return search


async def run_trending_search(
    search_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> TrendingSearch:
    search = session.get(TrendingSearch, search_id)
    _ensure_record_access(search, user, "Trending search", write=True)
    search.status = TaskStatus.running
    session.add(search)
    session.commit()

    credential = _active_platform_credential(session, search.platform, "trending")
    try:
        videos = await TrendingCollector(credential).collect(search)
    except Exception as exc:
        search.status = TaskStatus.failed
        search.notes = f"采集失败：{str(exc)[:400]}"
        session.add(search)
        session.commit()
        session.refresh(search)
        return search
    existing_videos = session.exec(select(TrendingVideo).where(TrendingVideo.search_id == search.id)).all()
    for existing_video in existing_videos:
        session.delete(existing_video)
    for video in videos:
        _assign_owner(video, user)
        session.add(video)
    search.status = TaskStatus.needs_review
    search.result_count = len(videos)
    session.add(search)
    session.commit()
    session.refresh(search)
    return search


def list_trending_searches(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[TrendingSearch]:
    statement = _owned_statement(select(TrendingSearch).order_by(TrendingSearch.created_at.desc()), TrendingSearch, user)
    return list(session.exec(statement).all())


def list_trending_videos(
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[TrendingVideo]:
    statement = _owned_statement(select(TrendingVideo).order_by(TrendingVideo.created_at.desc()), TrendingVideo, user)
    return list(session.exec(statement).all())


def create_trending_video(
    payload: TrendingVideoCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> TrendingVideo:
    _require_write_user(user)
    video = TrendingVideo.model_validate(payload)
    _assign_owner(video, user)
    session.add(video)
    session.commit()
    session.refresh(video)
    return video


router.post("/trending/searches", response_model=TrendingSearch)(create_trending_search)
router.post("/trending/searches/{search_id}/run", response_model=TrendingSearch)(run_trending_search)
router.get("/trending/searches", response_model=list[TrendingSearch])(list_trending_searches)
router.get("/trending/videos", response_model=list[TrendingVideo])(list_trending_videos)
router.post("/trending/videos", response_model=TrendingVideo)(create_trending_video)
