"""ZascArr — Entry point FastAPI."""
import asyncio
import contextlib
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from zascarr.config import get_settings

logger = structlog.get_logger()

STATIC_DIR = Path(__file__).parent / "static"


async def _import_loop(interval_minutes: int) -> None:
    """Job periódico del importador (B1/B3): organiza /downloads solo.

    Sin este loop, `import_interval_minutes` era un ajuste que nadie leía
    y el importador solo se ejecutaba si alguien lo invocaba a mano —
    la visión de "arrastro mi carpeta y el sistema se organiza solo" del
    backlog no existía en producción hasta ahora.
    """
    from zascarr.database import async_session_factory
    from zascarr.services.importer import Importer

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
    from zascarr.database import async_session_factory
    from zascarr.services.enricher import EnrichmentService

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


async def _orchestrator_loop(interval_minutes: int, limit: int) -> None:
    """Job periódico del orquestador (D1): wishlist → búsqueda en cascada
    → Transmission/aMule, y cierre del círculo (¿ya está en la biblioteca?).

    Sin este loop, `scan_interval_minutes`/`max_concurrent_downloads` eran
    ajustes que nadie leía y nada llamaba a `process_wishlist()` jamás —
    mismo bug de fondo que tenía el importador antes de B1/B3.
    """
    from zascarr.database import async_session_factory
    from zascarr.services.orchestrator import Orchestrator

    while True:
        try:
            async with async_session_factory() as session:
                orchestrator = Orchestrator(session)
                sent = await orchestrator.process_wishlist(limit=limit)
                imported = await orchestrator.check_completions(limit=limit)
                await session.commit()
            if sent or imported:
                logger.info("orchestrator.cycle_done", enviados=sent, importados=imported)
        except Exception:
            logger.exception("orchestrator.cycle_failed")
        await asyncio.sleep(interval_minutes * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("zascarr.starting", version=settings.app_version)
    from sqlalchemy import text

    from zascarr.database import engine
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("zascarr.db_connected")

    background_tasks = [
        asyncio.create_task(_import_loop(settings.import_interval_minutes)),
        asyncio.create_task(
            _enrichment_loop(settings.enrich_interval_minutes, settings.enrich_batch_size)
        ),
        asyncio.create_task(
            _orchestrator_loop(settings.scan_interval_minutes, settings.max_concurrent_downloads)
        ),
    ]

    yield

    for task in background_tasks:
        task.cancel()
    for task in background_tasks:
        with contextlib.suppress(asyncio.CancelledError):
            await task
    logger.info("zascarr.shutting_down")
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
    # Sin CORS: la UI (Jinja2/HTMX) y la API viven en el mismo origen, así que
    # no hay peticiones cross-origin legítimas. Un allow_origins=["*"] junto a
    # allow_credentials=True es inválido e inseguro según el spec CORS.

    from zascarr.api.health import router as health_router
    from zascarr.api.legal import router as legal_router
    from zascarr.api.series import router as series_router
    from zascarr.api.wishlist import router as wishlist_router
    from zascarr.web.dashboard import router as dashboard_router
    from zascarr.web.estado import router as estado_router
    from zascarr.web.legal import router as legal_ui_router
    from zascarr.web.library import router as library_router
    from zascarr.web.pendientes import router as pendientes_router
    from zascarr.web.routes import router as ui_router
    from zascarr.web.series import router as series_ui_router
    from zascarr.web.wishlist import router as wishlist_ui_router

    app.include_router(health_router, prefix="/api")
    app.include_router(legal_router)
    app.include_router(series_router, prefix="/api")
    app.include_router(wishlist_router, prefix="/api")
    app.include_router(ui_router)
    app.include_router(dashboard_router)
    app.include_router(estado_router)
    app.include_router(legal_ui_router)
    app.include_router(library_router)
    app.include_router(pendientes_router)
    app.include_router(series_ui_router)
    app.include_router(wishlist_ui_router)
    # Bug real (reportado): "/" mandaba a Estado (E1) en vez de a la
    # biblioteca — quien entra por primera vez esperaba ver su colección,
    # no un panel de semáforos técnico. Estado sigue disponible, en su
    # propia URL, enlazado desde la navegación (base.html).
    app.get("/", include_in_schema=False)(
        lambda: RedirectResponse("/ui/", status_code=307)
    )
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app


app = create_app()
