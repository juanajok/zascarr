"""SecuenciArr — Entry point FastAPI."""
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from secuenciarr.config import get_settings

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("secuenciarr.starting", version=settings.app_version)
    from secuenciarr.database import engine
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("secuenciarr.db_connected")
    yield
    logger.info("secuenciarr.shutting_down")
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Orquestador inteligente de tebeoteca digital.",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    from secuenciarr.api.health import router as health_router
    from secuenciarr.api.series import router as series_router
    from secuenciarr.api.wishlist import router as wishlist_router

    app.include_router(health_router, prefix="/api")
    app.include_router(series_router, prefix="/api")
    app.include_router(wishlist_router, prefix="/api")
    return app


app = create_app()
