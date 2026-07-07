from __future__ import annotations

from fastapi import APIRouter
from fastapi.routing import APIRoute

from app.api.module_registry import API_MODULES, module_for_path
from app.api.routes import router as legacy_router


def _module_router(module_key: str, label: str) -> APIRouter:
    return APIRouter(tags=[label], route_class=APIRoute)


def build_api_router() -> APIRouter:
    root = APIRouter()
    module_routers = {module.key: _module_router(module.key, module.label) for module in API_MODULES}

    for route in legacy_router.routes:
        if not isinstance(route, APIRoute):
            root.routes.append(route)
            continue
        module = module_for_path(route.path)
        route.tags = [module.label]
        module_routers[module.key].routes.append(route)

    for module in API_MODULES:
        root.include_router(module_routers[module.key])
    return root


api_router = build_api_router()
