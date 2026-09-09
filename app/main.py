"""应用工厂与入口：uvicorn app.main:app --reload（设计文档 §3）。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app.core.config import get_settings
from app.db import Base, get_session_factory, init_engine
from app.routers import ai, auth, charging, orders, scan, simulator, stations, stats, user, vehicle, ws
from app.seed import seed_if_empty
from app.services.charging import BizError

logger = logging.getLogger(__name__)


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
        # 三期 MQTT：MQTT_ENABLED=true 时激活（paho 线程，失败仅告警不阻断启动）
        consumer_started = False
        if settings.mqtt_enabled:
            from app.mqtt.consumer import start_consumer, stop_consumer
            try:
                start_consumer()
                consumer_started = True
            except Exception as exc:  # noqa: BLE001 - 连接失败不阻断 API
                logger.warning("MQTT consumer 启动失败（跳过）：%s", exc)
        # IoTDA 影子回环桥：IOTDA_ENABLED=true 时激活（上报模拟桩 + 收影子刷缓存）
        bridge_started = False
        if settings.iotda_enabled:
            from app.services.device_bridge import start_bridge, stop_bridge
            try:
                start_bridge()
                bridge_started = True
            except Exception as exc:  # noqa: BLE001 - 桥起不来不阻断 API
                logger.warning("IoTDA device_bridge 启动失败（跳过）：%s", exc)
        yield
        if consumer_started:
            stop_consumer()
        if bridge_started:
            stop_bridge()

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

    for module in (ai, auth, stations, charging, orders, scan, user, stats, vehicle, simulator):
        app.include_router(module.router, prefix=settings.api_prefix)
    app.include_router(ws.router, prefix=settings.api_prefix)
    return app


app = create_app()
