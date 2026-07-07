from __future__ import annotations

from fastapi import APIRouter
from fastapi.routing import APIRoute

from app.api.module_registry import api_module_by_key, module_for_path
from app.api.routes import router as legacy_router


def legacy_module_router(module_key: str) -> APIRouter:
    module = api_module_by_key(module_key)
    router = APIRouter(tags=[module.label], route_class=APIRoute)
    for route in legacy_router.routes:
        if not isinstance(route, APIRoute):
            continue
        if module_for_path(route.path).key != module.key:
            continue
        route.tags = [module.label]
        router.routes.append(route)
    return router
