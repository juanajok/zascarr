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

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr import database
from zascarr.database import get_db
from zascarr.models import ImportRun, Series
from zascarr.services import registro_biblioteca
from zascarr.services.library_adopter import EstadoAdopcion, LibraryAdopter
from zascarr.services.library_audit import LibraryAudit
from zascarr.web.routes import crear_templates

templates = crear_templates()


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


async def _fragmento_registro(request: Request, db: AsyncSession) -> HTMLResponse:
    """Lo que el coleccionista debe ver del registro AHORA: progreso, resultado o inventario previo."""
    reg = registro_biblioteca.estado_actual()
    contexto: dict = {"reg": reg, "estado": EstadoAdopcion.HECHA, "inv": None, "series": 0}
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
