"""FastAPI 应用入口。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.bootstrap import bootstrap
from app.config import get_settings
from app.database import create_all, get_session_factory
from app.errors import LUMIError
from app.llm import ProviderError
from app.routers import (
    characters,
    chat,
    conversations,
    devices,
    health,
    media,
    memory as memory_router,
    proactive as proactive_router,
    sync,
    world as world_router,
)
from app.security import build_auth_state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
logger = logging.getLogger("lumi")


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201
    settings = get_settings()
    try:
        app.state.auth = build_auth_state()
    except RuntimeError as exc:
        logger.error("%s", exc)
        raise

    # 1) 建表 + 原地迁移（绝不删库） 2) 播种内置人格与虚构生活
    create_all()
    factory = get_session_factory()
    with factory() as db:
        stats = bootstrap(db)
    logger.info("bootstrap: %s", stats)

    logger.info("LUMI v%s starting", __version__)
    logger.info("env=%s  db=%s", settings.env, settings.resolved_db_path)
    logger.info("provider=%s model=%s configured=%s",
                settings.provider, settings.provider_model, bool(settings.api_key))
    logger.info("auth=%s", app.state.auth.describe())
    if not settings.api_key:
        logger.warning(
            "LUMI_API_KEY 未配置：/api/v1/chat 将返回 503 provider_not_configured，"
            "不会返回任何伪造回复。"
        )
    yield
    logger.info("LUMI shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Project LUMI",
        version=__version__,
        description="LUMI v0.1 后端：真实模型驱动的 AI 少女聊天服务。",
        lifespan=lifespan,
    )

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(health.router)
    app.include_router(media.router)
    app.include_router(media.speech_router)
    app.include_router(chat.router)
    app.include_router(conversations.router)
    # v0.2
    app.include_router(devices.router)
    app.include_router(characters.router)
    app.include_router(memory_router.router)
    app.include_router(world_router.router)
    app.include_router(sync.router)
    app.include_router(proactive_router.router)

    @app.get("/", tags=["system"])
    def root() -> dict:
        return {
            "name": "Project LUMI",
            "version": __version__,
            "docs": "/docs",
            "health": "/api/v1/health",
        }

    @app.exception_handler(ProviderError)
    async def _provider_error_handler(request: Request, exc: ProviderError):  # noqa: ANN001, ARG001
        http_status, problem = exc.to_problem()
        return JSONResponse(
            status_code=http_status,
            content={"error": problem},
            headers={"X-LUMI-Error-Code": problem["code"]},
        )

    @app.exception_handler(LUMIError)
    async def _lum_error_handler(request: Request, exc: LUMIError):  # noqa: ANN001, ARG001
        http_status, problem = exc.to_problem()
        return JSONResponse(
            status_code=http_status,
            content={"error": problem},
            headers={"X-LUMI-Error-Code": problem["code"]},
        )

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException):  # noqa: ANN001, ARG001
        """统一错误信封：所有 4xx/5xx 都是 {"error": {"code","message","hint"}}。

        认证失败与限流都走这里，iOS 端只需解析一种结构。
        """
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail:
            body, code = detail, detail["code"]
        else:
            code = "http_error"
            body = {"code": code, "message": str(detail), "hint": None}

        headers = {"X-LUMI-Error-Code": code}
        headers.update(getattr(exc, "headers", None) or {})
        return JSONResponse(status_code=exc.status_code, content={"error": body}, headers=headers)

    return app


app = create_app()


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=settings.env.lower() == "dev",
        reload_dirs=[str(Path(__file__).resolve().parents[1])],
    )


if __name__ == "__main__":
    main()
