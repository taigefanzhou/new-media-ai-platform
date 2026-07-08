from __future__ import annotations

from fastapi import APIRouter

from app.api.digital_humans import (
    create_digital_human,
    create_digital_human_with_assets,
    create_volcengine_portrait_auth_session,
    delete_digital_human,
    get_volcengine_portrait_auth_status,
    list_digital_humans,
    sync_volcengine_portrait_auth_session,
    volcengine_portrait_auth_callback,
)
from app.models.entities import DigitalHuman


router = APIRouter(tags=["素材库与数字人"])


router.post("/digital-humans", response_model=DigitalHuman)(create_digital_human)
router.post("/digital-humans/create-with-assets", response_model=DigitalHuman)(create_digital_human_with_assets)
router.get("/digital-humans", response_model=list[DigitalHuman])(list_digital_humans)
router.post("/digital-humans/{human_id}/volcengine-auth/session")(create_volcengine_portrait_auth_session)
router.post("/digital-humans/{human_id}/volcengine-auth/sync")(sync_volcengine_portrait_auth_session)
router.get("/digital-humans/{human_id}/volcengine-auth/status")(get_volcengine_portrait_auth_status)
router.get("/volcengine/portrait-auth/callback", name="volcengine_portrait_auth_callback")(volcengine_portrait_auth_callback)
router.delete("/digital-humans/{human_id}")(delete_digital_human)
