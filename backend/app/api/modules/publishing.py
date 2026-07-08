from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import *  # noqa: F403


router = APIRouter(tags=["账号绑定与自动发布"])


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
