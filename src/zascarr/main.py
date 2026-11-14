"""ZascArr — Entry point FastAPI."""
import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import ProgrammingError

from zascarr.config import get_settings
from zascarr.services.ciclo_importador import ejecutar_ciclo_y_avisar
from zascarr.utils import lector_rar
from zascarr.utils.credenciales import CredencialesNoSegurasError, problema_de_credenciales
from zascarr.utils.log_acceso import instalar_filtro_de_acceso
from zascarr.utils.portada_rar import barrer_temporales

logger = structlog.get_logger()

# `httpx` registra cada petición a nivel INFO con la URL COMPLETA, y en Telegram
# esa URL lleva el token del bot (en ntfy, el tema hace de contraseña). La app no
# configura `logging`, así que hoy no se ven — pero cualquier manejador raíz o
# `--log-config` los sacaría. Se dejan explícitamente en WARNING para que no
# dependa de la configuración de fuera.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

STATIC_DIR = Path(__file__).parent / "static"


class RevalidatedStaticFiles(StaticFiles):
    """Estáticos que el navegador guarda pero comprueba en cada uso.

    Sin `Cache-Control`, el navegador decide por su cuenta cuánto tiempo reutiliza
    `/static/web.css` sin preguntar: tras una actualización seguía pintando la UI
    antigua (marca y tipografía) hasta forzar la recarga. Con `no-cache` pregunta
    siempre con el ETag que ya manda Starlette y, si nada cambió, recibe un 304 vacío:
    en la red de casa cuesta una petición sin cuerpo.
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


#: Compatibilidad: tests y código existente importan el nombre histórico desde `main`.
_ejecutar_ciclo_y_avisar = ejecutar_ciclo_y_avisar


async def _import_loop(interval_minutes: int) -> None:
    """Job periódico del importador (B1/B3): organiza /downloads solo.

    Sin este loop, `import_interval_minutes` era un ajuste que nadie leía
    y el importador solo se ejecutaba si alguien lo invocaba a mano —
    la visión de "arrastro mi carpeta y el sistema se organiza solo" del
    backlog no existía en producción hasta ahora.
    """
    from zascarr.database import async_session_factory
    from zascarr.services import comprobacion_disco

    while True:
        try:
            report = await comprobacion_disco.ejecutar_automatico(async_session_factory)
            # B7: la detección de desaparecidos revisa la biblioteca YA
            # importada, no las descargas — puede haber algo que avisar
            # aunque este ciclo no haya escaneado ningún fichero nuevo.
            if report is not None and (
                    report.files_scanned or report.disappeared_count or report.reappeared):
                logger.info(
                    "importer.cycle_done",
                    escaneados=report.files_scanned,
                    importados=report.imported_count,
                    duplicados=report.duplicate_count,
                    sin_clasificar=report.unsorted_count,
                    errores=report.error_count,
                    desaparecidos=report.disappeared_count,
                    reaparecidos=len(report.reappeared),
                )
        except Exception:
            logger.exception("importer.cycle_failed")
        await asyncio.sleep(interval_minutes * 60)


async def _rescan_loop(interval_minutes: int) -> None:
    """Job periódico del rescan de la biblioteca (BL-R9): registra lo nuevo
    (identificado → serie; si no → «Por revisar»), re-tría lo sustituido y
    marca/revierte lo desaparecido, sin consultar fuentes ni mover nada.

    El PRIMER paseo espera un intervalo completo: el primer rescan tras una actualización
    es el más caro (línea de base `file_mtime_ns` NULL: lee todos los CBZ una vez) y no debe
    competir con el arranque de la Pi; el checklist de despliegue recomienda lanzarlo a mano
    en un momento tranquilo. Comparte el cerrojo de ciclo con el importador: si coinciden,
    uno de los dos se salta ese turno (el rescan consta en el log y reintenta el siguiente).
    """
    from zascarr.database import async_session_factory
    from zascarr.services import rescan_biblioteca

    logger.info("rescan.first_delayed", minutos=interval_minutes)
    await asyncio.sleep(interval_minutes * 60)
    while True:
        try:
            informe = await rescan_biblioteca.ejecutar_automatico(async_session_factory)
            if informe is not None and (
                    informe.nuevos_entregados or informe.re_triados
                    or informe.desaparecidos or informe.reaparecidos):
                logger.info(
                    "rescan.cycle_done",
                    revisados=informe.files_scanned,
                    nuevos=informe.nuevos_registrados + informe.nuevos_a_revisar,
                    a_revisar=informe.nuevos_a_revisar,
                    re_triados=informe.re_triados,
                    reenlazados=informe.reenlazados,
                    desaparecidos=informe.desaparecidos,
                    reaparecidos=informe.reaparecidos,
                )
        except Exception:
            logger.exception("rescan.cycle_failed")
        await asyncio.sleep(interval_minutes * 60)


async def _upgrades_loop() -> None:
    """BL-D3: escaneo acotado de mejoras, con cadencia leída en cada vuelta.

    Se arranca siempre (salvo BD degradada) para que activar el escaneo o
    cambiar la cadencia en Ajustes funcione sin reiniciar. Si está desactivado
    o el perfil es «cualquiera», no consulta nada y solo espera.
    """
    from zascarr.database import async_session_factory
    from zascarr.services.upgrades import escanear_mejoras

    logger.info("upgrades.scheduler_started")
    siguiente: float | None = None
    intervalo_previo = -1
    bucle = asyncio.get_running_loop()
    while True:
        try:
            settings = get_settings()
            intervalo = max(0, int(getattr(settings, "upgrade_scan_interval_minutes", 0)))
            perfil = getattr(settings, "quality_profile", "equilibrado")
            ahora = bucle.time()
            if intervalo <= 0 or perfil == "cualquiera":
                siguiente = None
            else:
                if siguiente is None or intervalo != intervalo_previo:
                    # Primera vuelta (o cambio de cadencia): espera el intervalo nuevo.
                    siguiente = ahora + intervalo * 60
                if ahora >= siguiente:
                    async with async_session_factory() as db:
                        informe = await escanear_mejoras(db)
                        if informe.revisados or informe.creadas or informe.fallidos:
                            logger.info("upgrades.cycle_done",
                                        revisados=informe.revisados,
                                        creadas=informe.creadas,
                                        fallidos=informe.fallidos)
                    siguiente = bucle.time() + intervalo * 60
            intervalo_previo = intervalo
        except Exception:
            logger.exception("upgrades.cycle_failed")
        await asyncio.sleep(60)


async def _enrichment_loop(interval_minutes: int, batch_size: int) -> None:
    """Job periódico del enricher (B4): completa metadatos vía Comic Vine.

    Sesión propia por ciclo (no la de una request) y errores contenidos: un
    fallo puntual (Comic Vine caído, DB reiniciando) no debe tumbar el loop,
    solo saltarse ese ciclo y reintentar en el siguiente.
    """
    from zascarr.database import async_session_factory
    from zascarr.services.enricher import EnrichmentService
    from zascarr.utils.cache_http import purgar_cache

    while True:
        try:
            async with async_session_factory() as session:
                report = await EnrichmentService(session).enrich_pending(limit=batch_size)
                await session.commit()
            # SCR1: purga las filas caducadas de `http_cache` (nunca por `fresh_until`: eso
            # destruiría el ETag y el cuerpo que hacen posible el 304). `purgar_cache` ya
            # contiene el try/except: un fallo de purga no tumba el ciclo.
            await purgar_cache()
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
                # D8: primero se decide qué números quiere la política (y se
                # retira lo que ya no), y solo después se busca — así los items
                # recién generados entran en el mismo ciclo.
                politica = await orchestrator.sync_policy_items()
                sent = await orchestrator.process_wishlist(limit=limit)
                imported = await orchestrator.check_completions(limit=limit)
                await session.commit()
            if politica.generados or politica.retirados or sent or imported:
                logger.info(
                    "orchestrator.cycle_done",
                    generados=politica.generados,
                    retirados=politica.retirados,
                    enviados=sent,
                    importados=imported,
                )
        except Exception:
            logger.exception("orchestrator.cycle_failed")
        await asyncio.sleep(interval_minutes * 60)


async def _library_audit_task() -> None:
    """B16: AUDITA la biblioteca en el primer arranque; ya no la adopta.

    Hasta v1.4.8 esta tarea llamaba a LibraryAdopter directamente. El
    cambio viene de mirar una biblioteca real (2026-09-25): tenía
    carpetas duplicadas ENTERAS (la misma colección en dos rutas, ~140
    archivos), y adoptar sin avisar significaba que el dedupe por SHA256
    se quedaba con una copia y descartaba la otra **eligiendo por orden
    alfabético**. El coleccionista no llegaba a enterarse de que había
    una decisión que tomar. Decisión de producto: el sistema informa, la
    persona decide — la adopción pasa a dispararse a mano desde
    /ui/auditoria, con el informe delante.

    Tarea de UNA sola vez, no un loop: se lanza con los otros
    background_tasks pero termina sola, y cancelarla al apagar es un
    no-op si ya terminó."""
    from zascarr.database import async_session_factory
    from zascarr.services.library_adopter import LibraryAdopter
    from zascarr.services.library_audit import LibraryAudit

    try:
        async with async_session_factory() as session:
            # Mismo disparo que tenía la adopción: biblioteca con
            # contenido, catálogo vacío y no hecho ya antes.
            if not await LibraryAdopter(session).should_run():
                return
            logger.info("library_audit.starting")
            report = await LibraryAudit(session).run()
            await session.commit()
        logger.info(
            "library_audit.done",
            escaneados=report.files_scanned,
            hasheados=report.files_hashed,
            mismo_contenido=len(report.mismo_contenido),
            misma_obra=len(report.misma_obra),
            carpetas_repetidas=len(report.carpetas_repetidas),
            carpetas_vacias=len(report.carpetas_vacias),
        )
    except Exception:
        logger.exception("library_audit.failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("zascarr.starting", version=settings.app_version)
    # #418: observacional, no bloqueante (CLAUDE.md §3.2): sin `unar` solo faltan portadas de .cbr.
    if not settings.lector_rar_enabled:
        logger.info("lector_rar.apagado")
    elif not lector_rar.disponible():
        logger.warning("lector_rar.no_disponible")
    # B-4 (SecOps): temporales de lectura que dejó un proceso muerto (OOM, kill -9)
    huerfanos = await asyncio.to_thread(barrer_temporales, settings.covers_cache_path)
    if huerfanos:
        logger.info("lector_rar.temporales_barridos", cantidad=huerfanos)
    from sqlalchemy import text

    from zascarr.database import async_session_factory, engine

    # E6: arranque degradado. Si Postgres no conecta o el esquema no está, la
    # app arranca igual pero SOLO sirve diagnóstico (lo aplica AuthMiddleware
    # vía app.state.db_degraded). No se carga la configuración persistida
    # (p. ej. auth_mode guardado en runtime_settings): con credenciales o
    # configuración desconocidas se falla cerrado, no se abre una instalación
    # cuya autenticación estaba activada en BD.
    app.state.db_degraded = False
    try:
        # Credenciales por defecto: ni se intenta conectar (ADR 0012). El motivo no lleva el valor.
        # Se mira la URL del MOTOR (con la que de verdad se conectaría), no la de los ajustes.
        problema = problema_de_credenciales(engine.url) if hasattr(engine, "url") else None
        if problema:
            raise CredencialesNoSegurasError(f"{problema}; la aplicación no arranca con ella")
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))

        # D11: aplica los overrides de /ui/ajustes guardados en una ejecución
        # anterior — sin esto, tras un reinicio real (deploy, reboot de la Pi)
        # los ajustes seguirían en la BD pero no se verían hasta el primer
        # guardado nuevo desde la UI.
        from zascarr.services.runtime_settings import (
            RuntimeSettingsService,
            capturar_valores_base,
            load_overrides_at_startup,
        )
        # Seguridad: guarda el `BASE_URL` del `.env` antes de que los overrides
        # de la BD lo puedan pisar, para poder restaurarlo si Ajustes lo deja
        # vacío (vía de recuperación si el middleware da 403).
        capturar_valores_base()
        async with async_session_factory() as session:
            await load_overrides_at_startup(session)
            # A6: la cookie de sesión necesita una clave de firma estable —
            # se genera y persiste UNA vez, la primera vez que hace falta,
            # nunca hardcodeada ni dependiente de que alguien la ponga en
            # .env a mano.
            await RuntimeSettingsService(session).ensure_secret_key()
            await session.commit()
        logger.info("zascarr.db_connected")
    except Exception:
        logger.exception("zascarr.db_unavailable_at_startup")
        app.state.db_degraded = True

    if not app.state.db_degraded:
        # #478/#564: consumir el diario de conversión de una ejecución anterior. Si una
        # conversión murió entre apartar el original y publicar, se restaura; si murió
        # después de publicar, se repara la fila. Sin esto, el diario crecería sin fin.
        try:
            from zascarr.services.conversion import ConversionDeArchivo
            async with async_session_factory() as session:
                servicio = ConversionDeArchivo(session, secret=get_settings().secret_key)
                resueltas = await servicio.reconciliar_diario()
            if resueltas:
                logger.info("conversion.diario_reconciliado", resueltas=resueltas)
        except Exception:
            logger.exception("conversion.diario_reconciliacion_fallida")

    if app.state.db_degraded:
        # E6: «solo diagnóstico» también para el fondo. Sin BD, los cuatro ciclos
        # (auditoría, importación, enriquecimiento, orquestación) fallarían cada
        # intervalo sin poder hacer nada útil, y llenarían el log. No se arrancan.
        # Al reiniciar con la BD arreglada arrancan solos: no hay nada persistido
        # que desbloquear (la bandera es de este proceso).
        logger.warning("background_tasks_skipped_db_degraded", db_degraded=True)
        background_tasks = []
    else:
        # V6a (ADR 0006): continúa o cierra las asignaciones que quedaron vivas en una ejecución
        # anterior. Tarea de fondo (no retrasa el healthcheck) que nunca propaga una excepción.
        from zascarr.services.asignacion import comprobar_pool, reconciliar_al_arrancar
        if not comprobar_pool(engine, settings.asignacion_simultaneas):
            logger.warning("asignacion.pool_insuficiente",
                           simultaneas=settings.asignacion_simultaneas,
                           pool=settings.db_pool_size + settings.db_max_overflow)
        background_tasks = [
            asyncio.create_task(reconciliar_al_arrancar()),
            asyncio.create_task(_library_audit_task()),
            asyncio.create_task(_import_loop(settings.import_interval_minutes)),
            asyncio.create_task(
                _enrichment_loop(settings.enrich_interval_minutes, settings.enrich_batch_size)
            ),
            asyncio.create_task(_orchestrator_loop(
                settings.scan_interval_minutes, settings.max_concurrent_downloads
            )),
        ]
        # BL-R9: rescan periódico de la biblioteca; 0 lo desactiva.
        if settings.rescan_interval_minutes > 0:
            background_tasks.append(
                asyncio.create_task(_rescan_loop(settings.rescan_interval_minutes)))
        # BL-D3: siempre arranca; lee cadencia/perfil en cada vuelta para que
        # activar o desactivar en Ajustes no exija reiniciar.
        background_tasks.append(asyncio.create_task(_upgrades_loop()))

    yield

    # E6: al apagar (o al terminar un test que levantó la app degradada), se
    # restablece la bandera para no contaminar el siguiente arranque.
    app.state.db_degraded = False
    from zascarr.services.comprobacion_disco import detener as detener_comprobacion
    await detener_comprobacion()
    from zascarr.services.rescan_biblioteca import detener as detener_rescan
    await detener_rescan()
    for task in background_tasks:
        task.cancel()
    for task in background_tasks:
        with contextlib.suppress(asyncio.CancelledError):
            await task
    # Seguridad: apaga el ejecutor propio de PBKDF2 (no deja hilos ni tareas
    # encoladas colgando al parar la app).
    from zascarr.services.auth import apagar_ejecutor_pbkdf2
    apagar_ejecutor_pbkdf2()
    logger.info("zascarr.shutting_down")
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    # #361: el registro de acceso de uvicorn no lleva la query (carpetas, cursores, tokens).
    instalar_filtro_de_acceso()
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

    from starlette.exceptions import HTTPException as StarletteHTTPException

    from zascarr.api.estado import router as estado_cortesia_router
    from zascarr.api.exportacion import router as exportacion_api_router
    from zascarr.api.health import router as health_router
    from zascarr.api.legal import router as legal_router
    from zascarr.api.opds import router as opds_router
    from zascarr.api.operaciones import router as operaciones_router
    from zascarr.api.revision import router as revision_router
    from zascarr.api.series import router as series_router
    from zascarr.api.wishlist import router as wishlist_router
    from zascarr.services.auth import AuthMiddleware
    from zascarr.web.ajustes import router as ajustes_router
    from zascarr.web.arcos import router as arcos_ui_router
    from zascarr.web.asistente_carpetas import router as asistente_carpetas_router
    from zascarr.web.asistente_vinculacion import router as asistente_vinculacion_router
    from zascarr.web.asociar_fuente import router as asociar_fuente_ui_router
    from zascarr.web.auditoria import router as auditoria_router
    from zascarr.web.auth import router as auth_router
    from zascarr.web.colecciones import router as colecciones_ui_router
    from zascarr.web.contexto_declarado import router as contexto_declarado_router
    from zascarr.web.copias import router as copias_ui_router
    from zascarr.web.correspondencias_contexto import router as correspondencias_contexto_router
    from zascarr.web.dashboard import router as dashboard_router
    from zascarr.web.decisiones_reutilizables import router as decisiones_router
    from zascarr.web.desvinculacion import router as desvinculacion_ui_router
    from zascarr.web.discovery import router as discovery_router
    from zascarr.web.disponibilidad import router as disponibilidad_router
    from zascarr.web.errores import manejar_http, manejar_inesperado, pagina_error
    from zascarr.web.estado import router as estado_router
    from zascarr.web.exportar import router as exportar_router
    from zascarr.web.legal import router as legal_ui_router
    from zascarr.web.library import router as library_router
    from zascarr.web.mejoras import router as mejoras_ui_router
    from zascarr.web.navegacion import router as navegacion_router
    from zascarr.web.pendientes import router as pendientes_router
    from zascarr.web.retirada_serie import router as retirada_serie_ui_router
    from zascarr.web.routes import router as ui_router
    from zascarr.web.series import router as series_ui_router
    from zascarr.web.vistas_trabajo import router as vistas_router
    from zascarr.web.wishlist import router as wishlist_ui_router

    # A6: no-op mientras auth_mode="none" (por defecto) — se registra
    # siempre para que activarla desde /ui/ajustes no requiera reiniciar
    # el proceso con un middleware distinto.
    app.add_middleware(AuthMiddleware)

    app.include_router(health_router, prefix="/api")
    app.include_router(estado_cortesia_router, prefix="/api")
    app.include_router(legal_router)
    app.include_router(operaciones_router, prefix="/api")
    app.include_router(exportacion_api_router, prefix="/api")
    app.include_router(revision_router, prefix="/api")
    app.include_router(series_router, prefix="/api")
    app.include_router(opds_router)
    app.include_router(wishlist_router, prefix="/api")
    app.include_router(auth_router)
    app.include_router(ui_router)
    app.include_router(ajustes_router)
    app.include_router(auditoria_router)
    app.include_router(dashboard_router)
    app.include_router(discovery_router)
    app.include_router(estado_router)
    app.include_router(copias_ui_router)
    app.include_router(exportar_router)
    app.include_router(disponibilidad_router)
    app.include_router(legal_ui_router)
    app.include_router(navegacion_router)
    app.include_router(library_router)
    app.include_router(mejoras_ui_router)
    app.include_router(arcos_ui_router)
    app.include_router(asistente_carpetas_router)
    app.include_router(asistente_vinculacion_router)
    app.include_router(pendientes_router)
    app.include_router(correspondencias_contexto_router)
    app.include_router(contexto_declarado_router)
    app.include_router(decisiones_router)
    app.include_router(vistas_router)
    app.include_router(retirada_serie_ui_router)
    app.include_router(series_ui_router)
    app.include_router(asociar_fuente_ui_router)
    app.include_router(colecciones_ui_router)
    app.include_router(desvinculacion_ui_router)
    app.include_router(wishlist_ui_router)
    # Bug real (reportado): "/" mandaba a Estado (E1) en vez de a la
    # biblioteca — quien entra por primera vez esperaba ver su colección,
    # no un panel de semáforos técnico. Estado sigue disponible, en su
    # propia URL, enlazado desde la navegación (base.html).
    app.get("/", include_in_schema=False)(
        lambda: RedirectResponse("/ui/", status_code=307)
    )
    app.mount("/static", RevalidatedStaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.exception_handler(ProgrammingError)
    async def _esquema_incompleto_handler(request: Request, exc: ProgrammingError):
        """E6: una tabla ausente no debe ser un 500 crudo en /ui/*.

        `undefined_table` (SQLSTATE 42P01) es la firma de "conecta pero el
        esquema no está" (sin migrar o restauración a medias). Se degrada al
        mismo diagnóstico que /api/health en vez de reventar."""
        sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
        if sqlstate == "42P01":
            if request.url.path.startswith("/api/"):
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": (
                            "Esquema de base de datos incompleto o sin migrar"
                            " — consulta /api/health"
                        ),
                    },
                )
            return pagina_error(
                request, 503,
                mensaje="Base de datos no lista: le faltan partes o no se ha terminado de "
                        "actualizar. En el Estado verás qué hacer.",
            )
        raise exc

    # Página de error propia para quien navega (404, otros HTTPException y 500): la API y HTMX
    # conservan su respuesta. Ver web/errores.py.
    app.add_exception_handler(StarletteHTTPException, manejar_http)
    app.add_exception_handler(Exception, manejar_inesperado)

    return app


app = create_app()
