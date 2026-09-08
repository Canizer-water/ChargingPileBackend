"""应用工厂与入口：uvicorn app.main:app --reload（设计文档 §3）。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app.core.config import get_settings
from app.db import Base, get_session_factory, init_engine
from app.routers import auth, charging, orders, simulator, stations, ws
from app.seed import seed_if_empty
from app.services.charging import BizError


def _ensure_sqlite_dir(url: str) -> None:
    if url.startswith("sqlite"):
        # sqlite+aiosqlite:///./data/app.db → 取文件路径部分
        path = url.split("///", 1)[-1]
        parent = Path(path).parent
        if str(parent) not in ("", "."):
            Path(parent).mkdir(parents=True, exist_ok=True)


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        _ensure_sqlite_dir(settings.database_url)
        engine = init_engine(settings.database_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with get_session_factory()() as session:
            await seed_if_empty(session)
        yield

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(BizError)
    async def biz_error_handler(request: Request, exc: BizError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    async def index() -> RedirectResponse:
        """根路径友好入口：直接跳转交互式 API 文档（/docs）。"""
        return RedirectResponse(url="/docs")

    for module in (auth, stations, charging, orders, simulator):
        app.include_router(module.router, prefix=settings.api_prefix)
    app.include_router(ws.router, prefix=settings.api_prefix)
    return app


app = create_app()
