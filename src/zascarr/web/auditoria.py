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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.models import ImportRun
from zascarr.services.library_adopter import LibraryAdopter
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
    return templates.TemplateResponse(
        request, "auditoria.html",
        {"informe": informe, "adopcion_pendiente": await LibraryAdopter(db).should_run()},
    )


@router.post("/analizar", response_class=HTMLResponse)
async def analizar(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Relanza el análisis. Solo lectura del disco (ver LibraryAudit)."""
    await LibraryAudit(db).run()
    informe = await _ultimo_informe(db)
    return templates.TemplateResponse(
        request, "_auditoria_informe.html",
        {"informe": informe, "adopcion_pendiente": await LibraryAdopter(db).should_run()},
    )


@router.post("/adoptar", response_class=HTMLResponse)
async def adoptar(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """B11, ahora explícito: registra la biblioteca en el catálogo SIN
    mover ni renombrar nada. Irreversible solo en el sentido de que
    crea filas; los archivos del disco no se tocan."""
    adopter = LibraryAdopter(db)
    if not await adopter.should_run():
        return templates.TemplateResponse(
            request, "_auditoria_adopcion.html", {"report": None, "ya_hecha": True}
        )
    report = await adopter.adopt()
    return templates.TemplateResponse(
        request, "_auditoria_adopcion.html", {"report": report, "ya_hecha": False}
    )
