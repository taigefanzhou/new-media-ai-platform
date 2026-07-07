from __future__ import annotations

from fastapi import APIRouter

from app.api.modules import module_routers


def build_api_router() -> APIRouter:
    root = APIRouter()
    for module_router in module_routers:
        root.include_router(module_router)
    return root


api_router = build_api_router()
