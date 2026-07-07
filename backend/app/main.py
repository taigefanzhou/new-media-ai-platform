from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.api.routes import router
from app.core.auth import user_from_token
from app.core.config import get_settings
from app.core.db import engine, init_db
from sqlmodel import Session


settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def disable_static_cache(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if not path.startswith("/api/") and path.endswith((".html", ".js", ".css", "/")):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.middleware("http")
async def require_api_auth(request, call_next):
    path = request.url.path
    public_api_paths = {
        "/api/health",
        "/api/auth/login",
        "/api/auth/wechat/config",
        "/api/auth/wechat/start",
        "/api/auth/wechat/callback",
        "/api/volcengine/portrait-auth/callback",
    }
    if request.method == "OPTIONS" or not path.startswith("/api/") or path in public_api_paths:
        return await call_next(request)

    authorization = request.headers.get("authorization", "")
    token = ""
    if authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
    if not token:
        token = request.query_params.get("access_token", "").strip()
    if not token:
        return JSONResponse(status_code=401, content={"detail": "Missing authorization token"})

    with Session(engine) as session:
        try:
            user_from_token(token, session)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return await call_next(request)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


app.include_router(router, prefix="/api")
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
