"""api·应用工厂:平台 API 服务(服务化设计 §1-2)。

启动:uv run python -m trader.api [--port 8501]
dev:web/ 的 vite 代理到本服务;build 后本服务托管 web/dist(单进程部署)。
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from trader.api.auth import router as auth_router
from trader.api.resources import (docs_router, router as ledgers_router,
                                  runs_router, trading_router, watch_router)
from trader.api.systems import router as systems_router

_WEB_DIST = Path(__file__).resolve().parent.parent.parent / "web" / "dist"


def create_app() -> FastAPI:
    app = FastAPI(title="trader platform api", version="0.1")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # vite dev
        allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
    )
    app.include_router(auth_router)
    app.include_router(systems_router)
    app.include_router(ledgers_router)
    app.include_router(runs_router)
    app.include_router(trading_router)
    app.include_router(docs_router)
    app.include_router(watch_router)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    # FE build 产物托管(单进程部署;dev 期 dist 不存在则跳过)
    if _WEB_DIST.exists():
        app.mount("/", StaticFiles(directory=_WEB_DIST, html=True), name="web")
    return app


app = create_app()
