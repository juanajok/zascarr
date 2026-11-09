# ruff: noqa: E501
"""
Router de la auditoría de biblioteca (B16) — /ui/auditoria.

Enseña el informe de LibraryAudit y, solo desde aquí y solo a mano,
deja disparar la adopción (B11). El orden importa y es la historia
entera: primero el coleccionista ve qué hay repetido en su disco,
después decide adoptar. Hasta v1.4.8 la adopción saltaba sola en el
primer arranque y el dedupe elegía copia por orden alfabético sin que
nadie se enterara.

Esta pantalla NO borra ni mueve nada, ni ofrece hacerlo: las rutas
duplicadas se muestran para que el coleccionista actúe en su disco con
sus herramientas. Sugerir un borrado desde aquí sería justo la clase de
decisión irreversible que la historia se propone no tomar sola.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr import database
from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.models import ImportRun, Series
from zascarr.services import registro_biblioteca, rescan_biblioteca
from zascarr.services.aceptacion_adopcion import MAX_ILEGIBLES, aceptar, evaluar
from zascarr.services.library_adopter import EstadoAdopcion, InventarioBiblioteca, LibraryAdopter
from zascarr.services.library_audit import LibraryAudit
from zascarr.web.disponibilidad import registrar_filtros
from zascarr.web.routes import crear_templates

templates = crear_templates()
registrar_filtros(templates)


def _tamano(num_bytes: int | None) -> str:
    """Tamaño en la unidad que le sirve a una persona. Sin esto, la
    plantilla fijaba GB/MB y enseñaba "0.0 GB" o "0 MB cada uno" en
    cuanto los archivos eran pequeños — un número que no informa de
    nada y que además hace dudar de si el resto del informe es fiable."""
    b = num_bytes or 0
    if b >= 1024 ** 3:
        return f"{b / 1024 ** 3:.1f} GB"
    if b >= 1024 ** 2:
        return f"{b / 1024 ** 2:.0f} MB"
    if b >= 1024:
        return f"{b / 1024:.0f} KB"
    return f"{b} bytes"


templates.env.filters["tamano"] = _tamano

router = APIRouter(prefix="/ui/auditoria", tags=["ui"])


async def _ultimo_informe(db: AsyncSession) -> dict | None:
    run = (await db.execute(
        select(ImportRun)
        .where(ImportRun.details["kind"].astext == "audit")
        .order_by(ImportRun.started_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if not run:
        return None
    detalles = dict(run.details or {})
    detalles["started_at"] = run.started_at
    detalles["files_scanned"] = run.files_scanned
    return detalles


@router.get("", response_class=HTMLResponse)
async def index(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    informe = await _ultimo_informe(db)
    return templates.TemplateResponse(request, "auditoria.html", {"informe": informe})


@router.post("/analizar", response_class=HTMLResponse)
async def analizar(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Relanza el análisis. Solo lectura del disco (ver LibraryAudit)."""
    await LibraryAudit(db).run()
    informe = await _ultimo_informe(db)
    return templates.TemplateResponse(request, "_auditoria_informe.html", {"informe": informe})


async def _fragmento_registro(request: Request, db: AsyncSession, *, inc: InventarioBiblioteca | None = None,
                              cambio: bool = False, recien_aceptado: bool = False,
                              conflicto: bool = False) -> HTMLResponse:
    """Lo que el coleccionista debe ver del registro AHORA: progreso, resultado o inventario previo.
    `inc` (#326) es el inventario de archivos NUEVOS que se acaba de calcular a petición suya; `cambio`, que al confirmar la carpeta
    ya no era la que revisó; `recien_aceptado`, que la petición acaba de aceptar (para el foco); `conflicto`, que el intento
    no era válido y hay que enseñar el estado fresco."""
    reg = registro_biblioteca.estado_actual()
    contexto: dict = {"reg": reg, "estado": EstadoAdopcion.HECHA, "inv": None, "series": 0, "inc": inc,
                      "cambio": cambio, "adopcion": await evaluar(db, en_marcha=reg.en_marcha),
                      "recien_aceptado": recien_aceptado, "conflicto": conflicto}
    if reg.fase is registro_biblioteca.FaseRegistro.INACTIVO:
        adopter = LibraryAdopter(db)
        contexto["estado"] = await adopter.estado()
        if contexto["estado"] in (EstadoAdopcion.PENDIENTE, EstadoAdopcion.CATALOGO_PREVIO):
            contexto["inv"] = await adopter.inventario()
            contexto["series"] = (await db.execute(select(func.count(Series.id)))).scalar() or 0
    return templates.TemplateResponse(request, "_auditoria_registro.html", contexto)


@router.get("/registro", response_class=HTMLResponse)
async def registro(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Inventario previo, progreso o resultado del registro de la biblioteca. Solo lectura."""
    return await _fragmento_registro(request, db)


@router.post("/adoptar", response_class=HTMLResponse)
async def adoptar(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """B11, explícito: registra la biblioteca SIN mover ni renombrar nada, aunque ya haya series.

    Lanza el registro en segundo plano (ver `services/registro_biblioteca.py`) y devuelve el progreso; la
    página lo vuelve a pedir hasta que termina. Si ya hay uno en marcha no lanza otro. Repetirlo tras un
    fallo continúa donde se quedó."""
    en_marcha = registro_biblioteca.estado_actual().fase is registro_biblioteca.FaseRegistro.CORRIENDO
    if not en_marcha and await LibraryAdopter(db).puede_registrar():
        registro_biblioteca.iniciar(database.async_session_factory)
    return await _fragmento_registro(request, db)


@router.post("/aceptar-ilegibles", response_class=HTMLResponse)
async def aceptar_ilegibles(request: Request, run_id: UUID = Form(...),
                            count: int = Form(..., ge=1, le=MAX_ILEGIBLES),
                            db: AsyncSession = Depends(get_db)):
    """#332 residual 4: aceptación explícita de una adopción inicial incompleta.

    HTMX no intercambia 4xx: si el intento no vale, se devuelve el fragmento actualizado con 200 y
    el conflicto visible. Un cliente normal recibe 409/404 con el motivo, sin escribir nada."""
    resultado = await aceptar(db, run_id, count,
                              en_marcha=registro_biblioteca.estado_actual().en_marcha)
    if request.headers.get("HX-Request") == "true":
        return await _fragmento_registro(
            request, db, recien_aceptado=resultado.reason == "accepted",
            conflicto=not resultado.ok)
    if not resultado.ok:
        return JSONResponse({"reason": resultado.reason}, status_code=resultado.status)
    return await _fragmento_registro(request, db, recien_aceptado=True)


@router.get("/nuevos", response_class=HTMLResponse)
async def nuevos(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """#326: busca los archivos NUEVOS de la biblioteca ya registrada. Solo lectura: recorre nombres y rutas de la carpeta y las cruza con las
    registradas; no abre ningún archivo, no escribe en el catálogo y no pide nada a internet. Registrarlos es otro paso, con confirmación."""
    if registro_biblioteca.estado_actual().en_marcha or not await LibraryAdopter(db).ofrece_registro_incremental():
        return await _fragmento_registro(request, db)
    return await _fragmento_registro(request, db, inc=await LibraryAdopter(db).inventario())


@router.post("/registrar-nuevos", response_class=HTMLResponse)
async def registrar_nuevos(request: Request, huella: str = Form(...), db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """#326, explícito: registra SOLO los archivos nuevos que la persona vio y confirmó (la `huella` de esa lista). Si la carpeta ya no da la
    misma huella —apareció o desapareció algo desde que la revisó— no registra nada y enseña la lista de ahora. Sin mover ni renombrar nada,
    sin tocar lo ya registrado y sin repetir el registro inicial. Una sola ejecución a la vez, compartida con el registro inicial."""
    if registro_biblioteca.estado_actual().en_marcha:
        return await _fragmento_registro(request, db)
    adopter = LibraryAdopter(db)
    if not await adopter.ofrece_registro_incremental():
        return await _fragmento_registro(request, db)
    inv = await adopter.inventario()
    if not inv.se_puede_confirmar:       # carpeta ilegible, recorrido incompleto o nada que registrar: no se confirma nada global
        return await _fragmento_registro(request, db, inc=inv)
    if inv.huella != huella:
        return await _fragmento_registro(request, db, inc=inv, cambio=True)
    registro_biblioteca.iniciar(database.async_session_factory, alcance=inv.rutas_nuevas)
    return await _fragmento_registro(request, db)


# ── BL-R9: rescan de la biblioteca (a demanda; el periódico corre en main.py) ──

_CAMPOS_RESUMEN = (
    "files_scanned", "sin_cambios", "ya_registrados", "nuevos_entregados",
    "nuevos_registrados", "nuevos_a_revisar", "repetidos", "reenlazados",
    "re_triados", "re_triados_igual", "re_triados_cambiado",
    "re_triados_a_revisar", "re_triados_descartado", "copias_de_otra",
    "re_triados_protegidos", "discrepancias_registradas",
    "desaparecidos", "reaparecidos", "errores", "omitidos", "ambiguos",
    "no_revisado", "unreadable", "por_comprobar", "resultado_biblioteca",
)


def _resumen(informe) -> dict | None:
    """Normaliza el informe —en memoria (`RescanReport`) o persistido (dict de `_ultimo_rescan`)—
    a un dict para la plantilla. Un informe persistido debe pintarse igual que uno en memoria:
    tras un reinicio del proceso el estado en memoria ya no existe y la pantalla lee el `ImportRun`."""
    if informe is None:
        return None
    fuente = informe.get if isinstance(informe, dict) else (lambda c: getattr(informe, c, None))
    out: dict = {}
    for c in _CAMPOS_RESUMEN:
        v = fuente(c)
        if c in ("errores", "omitidos", "ambiguos") or isinstance(v, (list, tuple)):
            out[c] = list(v) if v else []
        elif isinstance(v, bool):
            out[c] = v
        elif isinstance(v, (int, float)):
            out[c] = v or 0
        else:
            out[c] = v or ""
    out["disparador"] = fuente("disparador") or "manual"
    out["started_at"] = fuente("started_at")
    return out


async def _ultimo_rescan(db: AsyncSession) -> dict | None:
    """El último rescan persistido (`kind="rescan"`), para una página recién cargada."""
    run = (await db.execute(
        select(ImportRun)
        .where(ImportRun.details["kind"].astext == "rescan")
        .order_by(ImportRun.started_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if not run:
        return None
    detalles = dict(run.details or {})
    detalles["started_at"] = run.started_at
    detalles["files_scanned"] = run.files_scanned
    detalles["errores"] = detalles.get("errores") or []
    return detalles


def _texto_cadencia() -> str:
    minutos = get_settings().rescan_interval_minutes
    if minutos <= 0:
        return "El rescan automático está apagado."
    if minutos == 1440:
        return "Además, ZascArr lo hace solo una vez al día."
    if minutos % 1440 == 0:
        return f"Además, ZascArr lo hace solo cada {minutos // 1440} días."
    if minutos % 60 == 0:
        return f"Además, ZascArr lo hace solo cada {minutos // 60} horas."
    return f"Además, ZascArr lo hace solo cada {minutos} minutos."


async def _contexto_rescan(db: AsyncSession, *, recien_lanzada: bool = False,
                           ya_en_curso: bool = False) -> dict:
    """Contexto común de página y fragmento; solo lee."""
    estado = rescan_biblioteca.estado_actual()
    resumen = _resumen(estado.informe)
    if resumen is None:
        resumen = await _ultimo_rescan(db)
    return {
        "estado_rescan": estado,
        "resumen": resumen,
        "cadencia": _texto_cadencia(),
        "recien_lanzada": recien_lanzada,
        "ya_en_curso": ya_en_curso,
        "recien_terminada": rescan_biblioteca.consumir_foco_resultado()
        if estado.fase is rescan_biblioteca.FaseRescan.TERMINADO else False,
    }


@router.get("/rescanear", response_class=HTMLResponse)
async def rescanear_estado(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Fragmento de estado del rescan. GET no lanza nada ni escribe: solo lee memoria e ImportRun."""
    contexto = await _contexto_rescan(db)
    respuesta = templates.TemplateResponse(request, "_rescan_biblioteca.html", contexto)
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.post("/rescanear", response_class=HTMLResponse)
async def rescanear(request: Request, db: AsyncSession = Depends(get_db)):
    """Lanza el rescan en segundo plano y responde ya. No espera a la operación."""
    lanzada = rescan_biblioteca.iniciar_manual(database.async_session_factory)
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse("/ui/auditoria", status_code=303)
    contexto = await _contexto_rescan(db, recien_lanzada=lanzada, ya_en_curso=not lanzada)
    respuesta = templates.TemplateResponse(request, "_rescan_biblioteca.html", contexto)
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta
