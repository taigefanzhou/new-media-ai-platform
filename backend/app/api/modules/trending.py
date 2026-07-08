from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import *  # noqa: F403


router = APIRouter(tags=["主题采集"])


router.post("/trending/searches", response_model=TrendingSearch)(create_trending_search)
router.post("/trending/searches/{search_id}/run", response_model=TrendingSearch)(run_trending_search)
router.get("/trending/searches", response_model=list[TrendingSearch])(list_trending_searches)
router.get("/trending/videos", response_model=list[TrendingVideo])(list_trending_videos)
router.post("/trending/videos", response_model=TrendingVideo)(create_trending_video)
