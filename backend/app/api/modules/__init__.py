from __future__ import annotations

from app.api.modules.digital_humans import router as digital_humans_router
from app.api.modules.publishing import router as publishing_router
from app.api.modules.reference_learning import router as reference_learning_router
from app.api.modules.script_creation import router as script_creation_router
from app.api.modules.system import router as system_router
from app.api.modules.trending import router as trending_router
from app.api.modules.video_library import router as video_library_router


module_routers = (
    system_router,
    reference_learning_router,
    script_creation_router,
    digital_humans_router,
    video_library_router,
    trending_router,
    publishing_router,
)
