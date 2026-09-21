"""SecuenciArr — Entry point FastAPI."""
import asyncio
import contextlib
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from secuenciarr.config import get_settings

logger = structlog.get_logger()

STATIC_DIR = Path(__file__).parent / "static"


async def _import_loop(interval_minutes: int) -> None:
    """Job periódico del importador (B1/B3): organiza /downloads solo.

    Sin este loop, `import_interval_minutes` era un ajuste que nadie leía
    y el importador solo se ejecutaba si alguien lo invocaba a mano —
    la visión de "arrastro mi carpeta y el sistema se organiza solo" del
    backlog no existía en producción hasta ahora.
    """
    from secuenciarr.database import async_session_factory
    from secuenciarr.services.importer import Importer

    while True:
        try:
            async with async_session_factory() as session:
                report = await Importer(session).scan_and_import()
                await session.commit()
            if report.files_scanned:
                logger.info(
                    "importer.cycle_done",
                    escaneados=report.files_scanned,
                    importados=report.imported_count,
                    duplicados=report.duplicate_count,
                    sin_clasificar=report.unsorted_count,
                    errores=report.error_count,
                )
        except Exception:
            logger.exception("importer.cycle_failed")
        await asyncio.sleep(interval_minutes * 60)


async def _enrichment_loop(interval_minutes: int, batch_size: int) -> None:
    """Job periódico del enricher (B4): completa metadatos vía Comic Vine.

    Sesión propia por ciclo (no la de una request) y errores contenidos: un
    fallo puntual (Comic Vine caído, DB reiniciando) no debe tumbar el loop,
    solo saltarse ese ciclo y reintentar en el siguiente.
    """
    from secuenciarr.database import async_session_factory
    from secuenciarr.services.enricher import EnrichmentService

    while True:
        try:
            async with async_session_factory() as session:
                report = await EnrichmentService(session).enrich_pending(limit=batch_size)
                await session.commit()
            if report.total_enriched or report.errors:
                logger.info(
                    "enricher.cycle_done",
                    enriched=report.total_enriched,
                    sin_match=len(report.series_no_match) + len(report.issues_no_match),
                    errores=len(report.errors),
                )
        except Exception:
            logger.exception("enricher.cycle_failed")
        await asyncio.sleep(interval_minutes * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("secuenciarr.starting", version=settings.app_version)
    from secuenciarr.database import engine
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("secuenciarr.db_connected")

    background_tasks = [
        asyncio.create_task(_import_loop(settings.import_interval_minutes)),
        asyncio.create_task(
            _enrichment_loop(settings.enrich_interval_minutes, settings.enrich_batch_size)
        ),
    ]

    yield

    for task in background_tasks:
        task.cancel()
    for task in background_tasks:
        with contextlib.suppress(asyncio.CancelledError):
            await task
    logger.info("secuenciarr.shutting_down")
    await engine.dispose()


async def dashboard() -> FileResponse:
    """E1: dashboard de estado en español con semáforos en vez de JSON crudo.

    Página única sin dependencias externas (nada de build tooling en una
    Pi): fetch() propio a /api/health, mismo origen, sin líos de CORS.
    """
    return FileResponse(STATIC_DIR / "dashboard.html")


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
    from secuenciarr.web.routes import router as ui_router

    app.include_router(health_router, prefix="/api")
    app.include_router(series_router, prefix="/api")
    app.include_router(wishlist_router, prefix="/api")
    app.include_router(ui_router)
    app.get("/", include_in_schema=False)(dashboard)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app


app = create_app()
