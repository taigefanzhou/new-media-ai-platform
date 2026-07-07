from __future__ import annotations

from fastapi import APIRouter
from fastapi.routing import APIRoute

from app.api.module_registry import api_module_by_key, module_for_path
from app.api.routes import router as legacy_router


def legacy_module_router(
    module_key: str,
    *,
    exclude_paths: set[str] | None = None,
    exclude_routes: set[tuple[str, str]] | None = None,
) -> APIRouter:
    module = api_module_by_key(module_key)
    excluded = exclude_paths or set()
    excluded_routes = {(path, method.upper()) for path, method in (exclude_routes or set())}
    router = APIRouter(tags=[module.label], route_class=APIRoute)
    for route in legacy_router.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path in excluded:
            continue
        if any((route.path, method.upper()) in excluded_routes for method in route.methods):
            continue
        if module_for_path(route.path).key != module.key:
            continue
        route.tags = [module.label]
        router.routes.append(route)
    return router
